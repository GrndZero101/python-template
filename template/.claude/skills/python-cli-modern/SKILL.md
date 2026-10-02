---
name: python-cli-modern
description: >-
  Conventions for modern devops CLI tools that call APIs — typer with Annotated, httpx clients,
  pydantic models, pydantic-settings configuration (flag, then env var, then default), rich output
  with a mandatory --output json path, loguru on stderr, shell completion, interactive prompts, and
  a switchable sequential/concurrent execution path. Use when the project depends on typer, httpx,
  rich, pydantic or loguru, when adding a command, a setting or an --output format, or when writing
  asyncio fan-out. Defers to python-cli for interface conventions.
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
| Configuration | `pydantic-settings` |
| Output and formatting | `rich` |
| Logging | `loguru` |
| Interactive prompts | `prompt_toolkit` |
| SQL Server / ORM | `SQLModel` |
| Concurrency | `asyncio`, `concurrent.futures` |

The scaffold depends on `typer`, `pydantic`, `pydantic-settings`, `rich` and `loguru` only. Add the
rest when the first command needs them — `uv add httpx`, never by editing `pyproject.toml`.

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

## The `--output` contract

Every command that emits data takes `--output`/`-o`. Minimum set: `table` (human) and `json`
(machine). Add `ndjson` for streams and `csv` where consumers want it.

```python
class OutputFormat(StrEnum):
    """How to render a command result."""

    table = "table"
    json = "json"
```

Declare a reusable annotated alias once, in `options.py`, then put it on **each command**. Its
default is `None`, not `table` — see **Configuration** below for why:

```python
OutputOption = Annotated[
    OutputFormat | None,
    typer.Option("--output", "-o", help=f"Output format. (env: {env_var('output')})"),
]


def ls(ctx: typer.Context, output: OutputOption = None) -> None:
    """List records."""
    settings = load_settings(verbose=global_options(ctx).verbose, output=output)
    emit(fetch_records(), settings.output)
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
asks — via `-o json` or the `<PREFIX>_OUTPUT=json` variable. This is deliberate: a tool that
silently emits JSON when redirected behaves differently in CI than in the terminal where you tested
it, and the failure is invisible. rich already honours `NO_COLOR` and `TERM=dumb`, so that half is
free.

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

## Configuration: flag, then environment variable, then default

Every setting resolves in that order, and `pydantic-settings` does the merge — never hand-roll it.
The scaffold's `config.py` is the worked instance:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, frozen=True, extra="forbid")

    verbose: bool = False
    output: OutputFormat = OutputFormat.table
```

The mechanism rests on one fact: **a value passed to the `Settings` constructor beats the
environment**, which beats the field default. So a flag wins simply by arriving as a constructor
argument — and an absent flag must not arrive at all. Hence:

- **Every option that maps to a setting defaults to `None`**, meaning "not given". A typer default of
  `False` or `table` is indistinguishable from the user typing it, and the environment variable
  could then never win.
- **`load_settings` drops the `None`s** before constructing. It builds the overrides in a
  `TypedDict`, not a `dict`: ty checks `Settings(**overrides)` against pydantic-settings' own
  typed `_env_prefix`-style parameters and rejects a loosely typed dict.
- **A boolean flag needs both halves**, `--verbose/--no-verbose`, typed `bool | None`. Without
  `--no-verbose` there is no way to override `VERBOSE=1` from the command line.
- **The prefix is the script name**, upper-cased: `my-tool` reads `MY_TOOL_OUTPUT`. A generic
  `CLI_OUTPUT` would be shared by every tool on the machine.
- **Do not also pass typer's `envvar=`.** click would parse the variable with its rules and
  pydantic with its own, and they disagree at the edges (`"yes"`, `"on"`). Name the variable in the
  help text instead, built from `env_var(field)` so it cannot drift. Write it `(env: NAME)`: typer
  renders help as rich markup, and `[env var: NAME]` is taken for a style tag and vanishes.
- **A validation failure exits 2** with a message naming the value, the flag *and* the variable,
  because the caller may have set either. `cli.main` maps `SettingsError` to that.
- **No `.env` file by default.** A stray `.env` in the working directory would change a test's
  outcome. Opt in with `env_file=".env"` when the tool genuinely needs it.
- **Tests clear the prefix.** The scaffold's `conftest.py` deletes every `<PREFIX>_*` variable
  before each test, so a developer's shell cannot make a test pass or fail.

Global options live on `@app.callback()`, which stores what it was given in a frozen
`GlobalOptions` on `ctx.obj`. Each command reads it back with `global_options(ctx)` and calls
`load_settings` once with its own flags added, so settings are validated in one place and the
command body sees a single typed `Settings`, never a raw `ctx.obj`.

Do not merge a command's overrides into existing settings with `model_copy(update=...)` — it skips
validation entirely. Construct a new `Settings`.

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
def fetch_records(client: httpx.Client, *, page_size: int = 100) -> Iterator[Record]:
    """Yield records, following pagination."""
```

Sequential and synchronous by default. Reach for `httpx.AsyncClient` only for fan-out, under
**Concurrency** below.

- **Inject the client.** Build it once at the command boundary, pass it down. Tests substitute
  `httpx.MockTransport`; nothing touches the network.
- **Timeouts are per-phase.** `httpx.Timeout(5.0, connect=2.0, read=30.0)` — a single float applies
  one value to all phases, which is rarely what a long-polling API needs.
- **`HTTPTransport(retries=N)` retries connection failures only — not 429 or 5xx.** Nearly
  everyone assumes otherwise. Status-code retry needs `tenacity` or an explicit loop, and must
  honour `Retry-After`.
- **Test through `httpx.MockTransport`**, never the network. A handler is a plain module-level
  function, bound with `functools.partial` rather than a lambda or a nested `def`:

  ```python
  def _respond(status: int, body: str, _request: httpx.Request) -> httpx.Response:
      return httpx.Response(status, text=body)


  def client_returning(body: str, status: int = 200) -> httpx.Client:
      handler = functools.partial(_respond, status, body)
      return httpx.Client(transport=httpx.MockTransport(handler))


  def test_parses_the_body() -> None:
      with client_returning('[{"id": 1}]') as client:
          assert list(fetch_records(client)) == [Record(id=1)]
  ```

  Also assert that a caller-supplied client is **not** closed by the function — it does not own it.

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

   **Through `main`, assert on captured stderr instead.** The app callback calls
   `configure_logging`, which removes every sink — including one a test added beforehand — and
   then adds one on `sys.stderr`, which by then is pytest's capture. So
   `assert "could not reach" in capsys.readouterr().err` works, and a pre-added sink silently
   receives nothing. Keep the sink approach for calling a plain function directly.
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
- **`pydantic-settings`** for configuration precedence — see **Configuration** above. Pass the
  resolved `Settings` down as a parameter; never read it from a module-level global.
- **SQLModel**: create the session at the command boundary and pass it down; never open one in a
  leaf function. Tests bind an in-memory SQLite engine.

### When the API shape is not the model shape

`Model.model_validate(raw)` works directly only when the API happens to return the field names the
model wants. Plenty of APIs do not — they nest the payload under a single-element list, or
name things `temp_C`, or return numbers as strings. The tempting response is to reshape a
`dict[str, Any]` by hand and hand the result to the model, which puts an `Any` in the signature and
gives up validation on the way in.

Use an **alias and a validator** instead, so the model still owns parsing:

```python
class Reading(BaseModel):
    """One observation, as this API happens to express it."""

    model_config = ConfigDict(populate_by_name=True)

    temperature_c: float = Field(alias="temp_C")
    humidity_percent: int = Field(alias="humidity")

    @field_validator("temperature_c", "humidity_percent", mode="before")
    @classmethod
    def _coerce_numeric_string(cls, value: object) -> object:
        """This API returns its numbers as strings; let pydantic do the conversion."""
        return value
```

When the interesting object is buried, index to it and validate *that* — the indexing expression is
typed, the reshaping is not:

```python
def parse_reading(payload: dict[str, list[dict[str, str]]]) -> Reading:
    """Return the current observation from a `j1`-style body."""
    current = payload["current_condition"][0]
    return Reading.model_validate(current)
```

Both keep `Any` out of the signature and keep validation at the boundary where it belongs. Reach
for `Any` only when the payload is genuinely unknown in shape, and say why in a comment.
