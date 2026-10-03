# typer in this stack

Why commands are declared the way the scaffold declares them. Read when a typer behaviour surprises
you, or before changing `cli.py` or `typer_entrypoint.py`.

## typer: `Annotated`, always

```python
@app.command()
def deploy(
    env: Annotated[str, typer.Argument(help="target environment")],
    retries: Annotated[int, typer.Option(min=0)] = 3,
    tags: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Deploy to an environment."""
```

Never the older default-value form (`retries: int = typer.Option(3)`). The convention hook's
`typer-default` rule refuses it, whatever the annotation. Ruff alone would not:

- **`B008`** fires on `typer.Option()` in a default slot only when the annotation is mutable or
  non-stdlib, so `str` and `int` escape it — and its advice, a module-level singleton, is the wrong
  fix for typer. `typer.Argument` and `typer.Option` are therefore listed in bugbear's
  `extend-immutable-calls`, which leaves `B008` on for everything else.
- **`FAST002` does not help.** It is FastAPI-specific and does not fire on typer code, despite the
  shapes looking identical.

With `Annotated` the call sits inside the annotation, and the real default after `=`:
`typer.Option(3)` becomes `= 3`, and `typer.Argument(...)` becomes no default at all.

Command bodies unpack and delegate. The decorated function belongs to typer; the work belongs in a
plain annotated function you can call with literal arguments.

### Reconciling typer with `main(argv) -> int`

`app()` calls `sys.exit` itself, which breaks the contract in **python-cli**. The scaffold's
`typer_entrypoint.run_app` calls it with `standalone_mode=False`, so typer **returns** instead, and
translates usage errors into exit codes. `cli.main` wraps it — use it as it is:

```python
def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    try:
        return run_app(app, argv, prog_name=PROG_NAME)
    except SettingsError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return USAGE_ERROR
```

Do not `import click` to catch its exceptions yourself. typer 0.27 vendors its own fork as
`typer._click`, the `click` package is not installed, and ty rejects the import. `run_app` is the
one place that private import lives.

Point `[project.scripts]` at this `main`, not at `app`. Now `main(["deploy", "dev"])` works from a
test, from pdb, and from the debug console. `typer.testing.CliRunner` is fine for asserting on
rendered output, but it captures streams and swallows tracebacks — prefer calling `main` for logic.

### No arguments shows help

```python
app = typer.Typer(no_args_is_help=True)
```

Multi-command groups already do this; set it explicitly because **a single-command app does not** —
it silently runs with all defaults, which for a deploy tool is a live incident.

`no_args_is_help` exits **2**. A bare invocation is a request for help, not a usage error, so
translate it to **0** in `main`; keep 2 for an unknown flag or subcommand. Also set
`no_args_is_help=True` on every sub-group.

A command missing a required argument is different: that **is** a usage error. `run_app` prints the
command's full help rather than click's terse one-liner, but to **stderr** and with exit **2**, so
`tool cmd && next` still stops and nothing lands in a pipe.

## The script name is never `cli`

On Windows, `cli` is a read-only PowerShell alias for `Clear-Item`, and an alias beats an
executable on PATH, so a command by that name is unreachable from the shell most Windows users are
in. It is not unique either: every project would install the same name into a shared environment.
The `script_name` question refuses it, and the scaffold reads the name from `config.PROG_NAME`.
