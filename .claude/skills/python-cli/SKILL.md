---
name: python-cli
description: >-
  Conventions for Python command-line tools — entrypoint shape, exit codes, the stdout/stderr
  split, argument parsing, and machine-readable output. Use when writing or changing a CLI,
  adding a subcommand or flag, wiring [project.scripts], deciding what a script should print,
  or making a module runnable from the terminal. Stack-agnostic: applies whether the parser is
  argparse, click or typer.
---

# Python CLI conventions

These are interface rules. They hold whatever the parser is — `argparse`, `click`, `typer`.
Dependency-specific guidance lives in the stack skills; this file is what they all defer to.

`src/claude/publicip.py` in this repo is a working reference for everything below.

## The entrypoint contract

```python
def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
```

Two properties, both load-bearing:

- **It takes `argv`.** Defaulting to `None` means `sys.argv[1:]` in production, but a test or a
  debug console can pass `main(["--timeout", "1"])` directly.
- **It returns rather than exits.** `sys.exit()` raises `SystemExit`, which unwinds your debugger
  session and forces tests into `pytest.raises` gymnastics or a subprocess.

Only the `__main__` block converts the return value into a process exit:

```python
if __name__ == "__main__":
    sys.exit(main())
```

Wire it up in `pyproject.toml` so it is a real command, not just a runnable file:

```toml
[project.scripts]
publicip = "claude.publicip:main"
```

Both entry paths must work: `uv run publicip` and `uv run python -m claude.publicip`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | runtime failure — network down, file missing, bad response |
| 2 | usage error — unknown flag, bad argument (argparse emits this itself) |

Reserve anything above 2 for conditions a caller would branch on, and document them in the
module docstring. Do not invent codes nobody scripts against.

## stdout is data, stderr is diagnostics

The single most important rule, because it is what makes a tool composable and what keeps agent
captures clean.

- **stdout** carries only the result — the thing a pipe consumes.
- **stderr** carries logs, progress, warnings, errors.

```python
# Right: the address is the data; the log line is not.
logger.debug("querying %s", url)
sys.stdout.write(f"{address}\n")
```

`T20` bans `print` in library code. In a CLI's output path, prefer `sys.stdout.write` — it is
explicit that you are writing *data to a stream*, and it does not fight the linter. If a module
genuinely needs `print`, add a narrow `per-file-ignores` entry for that module only, never
globally.

On the error path stdout must stay **empty**. A consumer doing `ip=$(publicip)` should get an
empty string and a non-zero status, never a half-written error message.

## Adapting to the terminal

Machine-readable when it is not a terminal, human-friendly when it is:

- Suppress colour, spinners and progress bars when `not sys.stdout.isatty()`.
- Offer `--json` for anything with structure. One object per invocation, or one per line for
  streams. This is what makes a tool scriptable and agent-friendly.
- Respect `NO_COLOR` if you emit colour at all.

## Verbosity maps to logging levels

Configure logging once, at the entrypoint, on stderr:

```python
logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)
```

`-v/--verbose` lowers the threshold, `-q/--quiet` raises it. Library modules call
`logger = logging.getLogger(__name__)` and never configure handlers themselves.

## Errors belong at the boundary

Library functions **raise**; only `main` decides what that means for the process:

```python
try:
    address = fetch_public_ip(url=args.url, timeout=args.timeout)
except httpx.HTTPError:
    logger.exception("could not reach %s", args.url)
    return 1
```

`logger.exception` keeps the traceback that says where it started. Never `sys.exit()` from
inside library code — it makes the function unusable from anything but a terminal.

## Structure

- Build the parser in its own `_build_parser() -> argparse.ArgumentParser`, so it can be tested
  and introspected without running anything.
- Subcommands read `tool verb [options] --flags`, e.g. `publicip show --json`. Pick verbs, keep
  them consistent, and don't overload one command with mutually exclusive flags.
- Keep the real work in importable functions with injected dependencies (client, clock, paths).
  `main` should read as: parse → call → format → return.

## Testing a CLI

No subprocess, no network:

```python
def test_main_prints_address_to_stdout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "claude.publicip.fetch_public_ip", functools.partial(_always, "203.0.113.7")
    )
    assert main([]) == 0
    assert capsys.readouterr().out == "203.0.113.7\n"
```

Assert on the **exit code** and on **stdout separately from stderr** — that is what pins the
contract above. Note that pytest installs its own logging handler, so `logging.basicConfig` in
`main` becomes a no-op: assert log output via `caplog`, not `capsys`.
