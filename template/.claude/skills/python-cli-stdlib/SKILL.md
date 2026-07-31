---
name: python-cli-stdlib
description: >-
  Dependency policy and argparse patterns for CLI tools built on the standard library with minimal
  external dependencies. Use when the project declares a stdlib-only or minimal-dependency policy,
  when writing argparse parsers and subcommands, or when deciding whether a new third-party
  dependency is justified. Defers to python-cli for interface conventions.
---

# Stdlib CLI conventions

Interface rules — entrypoint shape, exit codes, the stdout/stderr split — live in **python-cli**.
This skill covers only what is specific to a stdlib-first dependency policy and to `argparse`.

## The dependency policy

Default to the standard library. Every dependency is a supply-chain surface, a version constraint,
and something a reader has to already know. Add one when the stdlib answer would mean
reimplementing something genuinely hard — not when it would merely mean writing more code.

| Need | Use from stdlib | Reach for a dependency when |
|---|---|---|
| argument parsing | `argparse` | never — it does subcommands, groups, mutual exclusion |
| paths | `pathlib` | never |
| structured data | `dataclasses`, `NamedTuple` | you must validate *untrusted* input → then you are `cli-modern` |
| dates | `datetime` + `zoneinfo` | never |
| read TOML | `tomllib` | you need to *write* TOML → `tomli-w` |
| JSON | `json` | you need speed on large payloads → `orjson` |
| SQL | `sqlite3` | a different engine |
| parallelism | `concurrent.futures` | never for CLI-scale work |
| subprocesses | `subprocess` | never |
| HTTP | `urllib.request` | see below |
| colour, tables, progress | manual ANSI | you want real layout → `rich` |
| retry policy | an explicit `for` loop | the policy grows backoff + jitter + conditions → `tenacity` |

**HTTP is the honest exception.** `urllib.request` has no connection reuse, no per-phase timeouts,
a clumsy error hierarchy, and no HTTP/2. For a single unauthenticated GET it is fine. Past that,
`httpx` is justified — which is why `src/claude/publicip.py` in this repo uses it. State the reason
in the commit body when you add one.

## argparse patterns

Build the parser in its own function so it can be tested and introspected without running anything:

```python
def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(prog="tool", description="What it does.")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds")
    return parser
```

Let `argparse` do the work rather than validating by hand afterwards:

- `type=` takes any callable — `type=Path`, `type=float`, or your own
  `_positive_int(raw: str) -> int` that raises `argparse.ArgumentTypeError`.
- `choices=` for a fixed set. Never re-check a `choices` value in the body.
- `required=True` on options that are not optional, rather than a post-parse `if x is None`.
- Defaults belong in `add_argument`, not scattered through the body.

`argparse` already exits **2** with a usage message on a bad argument. Do not catch that and
re-report it; the exit code table in **python-cli** depends on it.

### Subcommands

Read `tool verb [options] --flags`. Attach the handler as a real function object:

```python
def _add_sync_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `sync` subcommand."""
    parser = subparsers.add_parser("sync", help="copy records upstream")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(handler=handle_sync)
```

Then `main` is two lines of dispatch:

```python
args = _build_parser().parse_args(argv)
return args.handler(args)
```

This is dispatch through a stored **function reference**, not `getattr` on a name — grep for
`handle_sync` finds both the registration and the definition, and a breakpoint on it holds. That is
the distinction CLAUDE.md's "no dynamic dispatch" rule is drawing; this side of it is fine.

Give every subcommand its own `_add_*_command` registrar and its own module-level
`handle_*(args) -> int`. One module per verb once there are more than about three.

## Keep the work out of the parser

`argparse.Namespace` is an untyped bag. Do not let it travel:

```python
def handle_sync(args: argparse.Namespace) -> int:
    """Unpack argv and delegate. Returns an exit code."""
    return sync_records(source=args.source, dry_run=args.dry_run)
```

`sync_records` takes real typed parameters, is annotated, and is callable from a breakpoint with
literal arguments. The `Namespace` stops at the boundary. This is what makes the tool testable
without constructing fake namespaces.

## Testing

No subprocess, no network — call `main(argv)` directly, as **python-cli** describes.

For HTTP under `urllib.request`, inject the opener rather than patching the module:

```python
def fetch(url: str, opener: urllib.request.OpenerDirector | None = None) -> str:
```

For `subprocess`, inject a runner parameter defaulting to `subprocess.run`. Both keep the test
offline and let you substitute a value from the debug console.
