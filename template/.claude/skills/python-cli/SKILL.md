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
How to implement them on a given stack — the parser, the logger, how to test log output — lives in
the stack skill (**python-cli-modern** or **python-cli-stdlib**). Where the two seem to disagree,
the stack skill is the one that has been run against the scaffold; follow it.

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
my-tool = "my_tool.cli:main"
```

Both entry paths must work: `uv run my-tool` and `uv run python -m my_tool.cli`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success, including a bare invocation that prints help |
| 1 | runtime failure — network down, file missing, bad response |
| 2 | usage error — unknown flag, bad argument, invalid setting |

Reserve anything above 2 for conditions a caller would branch on, and document them in the
module docstring. Do not invent codes nobody scripts against.

## stdout is data, stderr is diagnostics

The single most important rule, because it is what makes a tool composable and what keeps agent
captures clean.

- **stdout** carries only the result — the thing a pipe consumes.
- **stderr** carries logs, progress, warnings, errors.

```python
sys.stdout.write(f"{address}\n")  # the address is the data
```

Diagnostics go through the logger, which is configured on stderr. The call style depends on the
library, and getting it wrong prints a literal placeholder rather than failing:

| Library | Call |
|---|---|
| stdlib `logging` | `logger.debug("querying %s", url)` |
| `loguru` | `logger.debug("querying {}", url)` |

`T20` bans `print` everywhere, `__main__` blocks included. In a CLI's output path, use
`sys.stdout.write` — it is explicit that you are writing *data to a stream*, and it does not fight
the linter. If a module genuinely needs `print`, add a narrow `per-file-ignores` entry for that
module only, never globally.

On the error path stdout must stay **empty**. A consumer doing `ip=$(my-tool ip)` should get an
empty string and a non-zero status, never a half-written error message.

## Output formats

- **Every command that emits data takes `--output`/`-o`**, with at least `table` for people and
  `json` for programs. One JSON object or array per invocation; `ndjson` for streams. This is
  what makes a tool scriptable and agent-friendly. Do not add a separate `--json` flag that can
  contradict it.
- **The format never changes on its own.** `table` on a terminal, `table` in a pipe. Only the
  caller changes it, with the flag or its environment variable. A tool that silently emits JSON
  when redirected behaves differently in CI than in the terminal where it was tested, and the
  failure is invisible.
- **Decoration does adapt.** Suppress colour, spinners and progress bars when the stream they
  would write to is not a terminal, and respect `NO_COLOR`.

## Verbosity

`-v/--verbose` lowers the logging threshold; `-q/--quiet`, if offered, raises it. Configure logging
once, at the entrypoint, on stderr. Library modules never configure handlers themselves.

## Errors belong at the boundary

Library functions **raise**; only `main` decides what that means for the process:

```python
try:
    address = fetch_public_ip(client)
except httpx.HTTPError:
    logger.exception("could not reach the address service")
    return 1
```

`logger.exception` keeps the traceback that says where it started, and works the same in stdlib
`logging` and `loguru`. Never `sys.exit()` from inside library code — it makes the function
unusable from anything but a terminal.

## Structure

- Subcommands read `tool verb [options]`, e.g. `my-tool records --output json`. Pick verbs, keep
  them consistent, and do not overload one command with mutually exclusive flags.
- Keep the real work in importable functions with injected dependencies (client, clock, paths).
  A command reads as: parse → call → format → return.

## Testing a CLI

No subprocess, no network. Call `main` with an argv list and assert on three things separately —
the **exit code**, **stdout** and **stderr**:

```python
def test_records_json_is_parseable(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["records", "--output", "json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == [{"id": 1}]
    assert captured.err == ""
```

That is what pins the contract above. How to assert on *log* output depends on the logging
library — `caplog` works for stdlib `logging` and silently sees nothing under `loguru` — so the
stack skill says which to use.
