---
name: python-cli-modern
description: >-
  Conventions for modern devops CLI tools that call APIs — typer with Annotated, httpx clients,
  pydantic models, rich output with a mandatory --output json path, loguru on stderr, shell
  completion, interactive prompts, and a switchable sequential/concurrent execution path. Use when
  the project depends on typer, httpx, rich, pydantic or loguru, when adding a command or an
  --output format, or when writing asyncio fan-out. Defers to python-cli for interface conventions.
---

# Modern CLI conventions

Interface rules — entrypoint shape, exit codes, the stdout/stderr split — live in **python-cli**.
Dataframe and analytics guidance lives in **python-data**. This skill covers the API-calling devops
CLI: a tool that talks to remote services and whose output has to be consumable by both a human and
a script.

Pick this stack deliberately. For a two-flag tool with no API calls, **python-cli-stdlib** produces
less to read.

## Preferred packages

| Purpose | Package |
|---|---|
| API calls | `httpx` |
| Argument processing | `typer` |
| Data structures | `pydantic` |
| Output and formatting | `rich` |
| Logging | `loguru` |
| Interactive prompts | `prompt_toolkit` |
| SQL Server / ORM | `SQLModel` |
| Concurrency | `asyncio`, `concurrent.futures` |

**Use a trusted vendor SDK before rolling your own client.** If `boto3`, `google-cloud-*`,
`azure-*`, `PyGithub`, `kubernetes` or similar covers the service, use it — it already handles auth
refresh, pagination and retry semantics you would get subtly wrong. Reach for `httpx` when there is
no credible SDK, or when the SDK is a thin wrapper over a REST endpoint you use one route of. Either
way the client is a **parameter with a default**, never a module-level singleton, so the function
stays re-runnable from a breakpoint.

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

Never the older default-value form (`retries: int = typer.Option(3)`). The lint story is a partial
trap:

- **`B008`** fires on `typer.Option()` in a default slot — but *only* when the annotation is mutable
  or non-stdlib. `str` and `int` escape it. So a codebase in the old style lints clean until the
  first `list[str]` option, and by then the fix is a signature rewrite.
- **`FAST002` does not help.** It is FastAPI-specific and does not fire on typer code, despite the
  shapes looking identical. Do not expect the linter to catch this.

With `Annotated` the call sits inside the annotation rather than the default slot, so `B008` cannot
fire. Do **not** relax `B008` for a CLI module to permit the old style — it is a real bug detector
for ordinary code in the same file, and `Annotated` removes the need entirely.

Command bodies unpack and delegate. The decorated function belongs to typer; the work belongs in a
plain annotated function you can call with literal arguments.

### Reconciling typer with `main(argv) -> int`

`app()` calls `sys.exit` itself, which breaks the contract in **python-cli**. Pass
`standalone_mode=False` and typer **returns** instead:

```python
def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    try:
        app(args=argv, standalone_mode=False, prog_name="tool")
    except click.ClickException as exc:
        exc.show()
        return 2
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    return 0
```

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

## The `--output` contract

Every command that emits data takes `--output`/`-o`. Minimum set: `table` (human) and `json`
(machine). Add `ndjson` for streams and `csv` where consumers want it.

```python
class OutputFormat(str, Enum):
    """How to render command results."""

    table = "table"
    json = "json"
```

Declare a reusable annotated alias once, then put it on **each command**:

```python
OutputOption = Annotated[
    OutputFormat, typer.Option("--output", "-o", envvar="TOOL_OUTPUT", help="output format")
]


@app.command()
def ls(output: OutputOption = OutputFormat.table) -> None:
    """List records."""
```

**Do not declare `--output` only on `@app.callback()`.** A callback option is parsed at the *group*
level, so `tool -o json ls` works but `tool ls -o json` fails with `No such option: -o` — and the
second is where people actually type it. Verified on typer 0.27. The alias costs one line per
command and puts the flag where it is expected.

Reserve the callback for options that genuinely belong to the group, like `--verbose` or
`--config`. If you want `--output` accepted in both positions, you need it in both places plus
explicit precedence — usually not worth the ambiguity.

**The default never changes on its own.** `table` on a terminal, `table` in a pipe. Colour and
spinners auto-suppress when stdout is not a tty, but the *data format* only changes when the caller
asks — via `-o json` or `TOOL_OUTPUT=json`. This is deliberate: a tool that silently emits JSON when
redirected behaves differently in CI than in the terminal where you tested it, and the failure is
invisible. rich already honours `NO_COLOR` and `TERM=dumb`, so that half is free.

For `json`, write it directly rather than through rich — no console configuration can then break it:

```python
def emit(rows: list[Record], fmt: OutputFormat, console: Console) -> None:
    """Write results to stdout in the requested format."""
    if fmt is OutputFormat.json:
        sys.stdout.write(json.dumps([r.model_dump(mode="json") for r in rows]) + "\n")
        return
    console.print(_build_table(rows))
```

One JSON object or array per invocation. On the error path stdout stays **empty**.

## Two rich consoles — the sharpest edge in this stack

`rich.Console()` writes to **stdout** by default, and so do `Progress` and `status`. So the obvious
`console.print("Fetching…")` silently corrupts the stream a caller is parsing. Declare both, once:

```python
out = Console()  # data only — stdout
err = Console(stderr=True)  # progress, status, human-facing errors
```

Everything decorative goes to `err`. Progress bars must also disable themselves when there is no
terminal, or CI logs fill with redraw frames:

```python
with Progress(console=err, disable=not err.is_terminal) as progress:
    ...
```

If you find yourself passing `out` to anything other than the final result render, that is the bug.

## httpx

```python
async def fetch_records(
    client: httpx.AsyncClient,
    *,
    page_size: int = 100,
) -> AsyncIterator[Record]:
    """Yield records, following pagination."""
```

- **Inject the client.** Build it once at the command boundary, pass it down. Tests substitute
  `httpx.MockTransport`; nothing touches the network.
- **Timeouts are per-phase.** `httpx.Timeout(5.0, connect=2.0, read=30.0)` — a single float applies
  one value to all phases, which is rarely what a long-polling API needs.
- **`AsyncHTTPTransport(retries=N)` retries connection failures only — not 429 or 5xx.** Nearly
  everyone assumes otherwise. Status-code retry needs `tenacity` or an explicit loop, and must
  honour `Retry-After`.
- Pagination is a generator that yields records, not a function returning an accumulated list. The
  caller then streams and a `--limit` can stop early.
- `response.raise_for_status()` at the boundary; let the domain function raise and let `main` decide
  the exit code.

## loguru: three duties

loguru replaces stdlib `logging` rather than configuring it, so ruff's `LOG`/`G` rules stop applying
to loguru call sites. CLAUDE.md permits it for this stack; in exchange, all three of these are
mandatory.

1. **Route stdlib logging into it.** Your dependencies — httpx, SDKs — still use `logging`, and
   without an `InterceptHandler` their output vanishes. Put the canonical handler in its own
   `logging_setup.py` and call it once from `main`. It is vendored boilerplate with a frame-walking
   loop; it is not an example of house style.
2. **`caplog` does not work.** loguru does not propagate to pytest's handlers, so log assertions
   silently pass against empty text. Add the documented `propagate_logs` autouse fixture to
   `conftest.py`, or assert through a `logger.add(records.append)` sink.
3. **`logger.catch(reraise=True)`, always.** A bare `logger.catch` swallows the exception — the same
   defect as `except: pass`.

loguru's default sink is already `stderr`; never move it to stdout.

## Concurrency: always a switchable sequential path

Any fan-out gets a `--concurrency N` option, where **`N=1` takes a genuinely sequential code
path** — not a `TaskGroup` with a semaphore of 1:

```python
async def map_limited(
    items: Sequence[T],
    call: Callable[[T], Awaitable[R]],
    *,
    concurrency: int,
) -> list[R]:
    """Apply `call` to every item, strictly sequentially when concurrency == 1."""
    if concurrency == 1:
        results: list[R] = []
        for item in items:
            results.append(await call(item))  # noqa: PERF401
        return results
    return await _map_concurrent(items, call, limit=concurrency)
```

The explicit loop is the point, so `PERF401` gets suppressed here rather than obeyed. Why `N=1` must
be a separate path:

- A semaphore of 1 still interleaves task switches, so logs from different items still braid
  together and the order shifts between runs.
- `TaskGroup` wraps failures in an **`ExceptionGroup`**, so `except SomeError` stops matching and you
  need `except*`. The sequential path raises the bare exception, with one frame stack that leads
  straight to the failing item.
- A traceback through `gather` tells you a task failed; a traceback through the loop tells you *which
  input* failed.

Make `1` easy to reach and say so in the `--concurrency` help text. One knob, not a separate
`--sequential` flag that can contradict it.

Use `asyncio` for I/O-bound API calls and `concurrent.futures.ThreadPoolExecutor` for blocking
libraries. Never call a blocking client from inside a coroutine — `asyncio.to_thread` if you must.

## Interactive prompts

`prompt_toolkit` (optionally `questionary` on top of it) for confirm, select and autocomplete inside
a normal command. Full-screen applications are **python-tui**.

A prompt in a non-interactive context is a **hang**, not an error, so guard every one:

- Prompt only when `sys.stdin.isatty() and sys.stderr.isatty()`.
- **Never prompt when `-o json`** — a machine consumer cannot answer.
- `--yes` to assume confirmation; `--no-input` to fail rather than ask.
- With no tty and no `--yes`, exit **2** with a message naming the flag that would have avoided it:
  `"refusing to prompt without a terminal; pass --yes to confirm"`.
- **Route the prompt to stderr.** `prompt_toolkit` writes to stdout by default, which corrupts the
  data stream: `create_output(stdout=sys.stderr)`.

Keep the answer collection separate from the action, so the action stays callable with literal
arguments and the tests never prompt.

## Shell completion — do not ship `--install-completion`

Typer's installer is destructive and wrong under a custom `$ZDOTDIR`
(`typer/_completion_shared.py`, verified in 0.27.0):

- `zshrc_path = Path.home() / ".zshrc"` — **`$ZDOTDIR` is never consulted**, so with a custom
  location it writes to a file zsh never reads.
- It **rewrites your `.zshrc`** with `write_text` and no backup.
- It appends an unconditional `fpath+=~/.zfunc; autoload -Uz compinit; compinit`, which double-runs
  `compinit` if you already use oh-my-zsh, zinit or a compiled zcompdump.
- It gates its `zstyle` injection on a naive `"zstyle" not in content` check over the whole file.

So disable it and emit the script to stdout instead, letting the user or the package manager place
it:

```python
app = typer.Typer(add_completion=False)
```

```bash
# note: source_zsh, NOT zsh_source — typer inverts Click 8's order for back-compat
_TOOL_COMPLETE=source_zsh tool > "${ZDOTDIR:-$HOME}/completions/_tool"
```

That output is a clean `#compdef` block with no `fpath` or `compinit` lines. The env var is derived
from the program name, uppercased — so a `prog_name` containing a dot yields an invalid variable;
rely on the `[project.scripts]` name. `source_bash`, `source_fish` and `source_powershell` work the
same way.

Document this in the README. `--show-completion` is not a substitute: it uses shellingham to detect
the *parent process*, so it cannot cross-generate another shell's script.

## pydantic and SQLModel

- **`BaseModel`** at the edges — API responses, config files, anything untrusted. Validate once on
  the way in, then pass the validated object around; do not re-validate in every function.
- **`dataclass`** for everything internal, per CLAUDE.md. Cheaper, and its `repr` is just as
  readable in the debugger.
- **`pydantic-settings`** for configuration precedence (flag > env > file > default) rather than a
  hand-rolled merge. Inject the settings object as a parameter with a default.
- **SQLModel**: create the session at the command boundary and pass it down; never open one in a
  leaf function. Tests bind an in-memory SQLite engine.
