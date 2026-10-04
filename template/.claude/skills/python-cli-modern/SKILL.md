---
name: python-cli-modern
description: >-
  Recipes and conventions for modern devops CLI tools that call APIs — typer with Annotated, httpx
  clients, pydantic models, pydantic-settings configuration (flag, env var, YAML file, default), rich
  output with a mandatory --output json path, loguru on stderr, shell completion, interactive
  prompts, and a switchable sequential/concurrent execution path. Use when the project depends on
  typer, httpx, rich, pydantic or loguru, when adding a command, a setting or an --output format,
  or when writing asyncio fan-out. Defers to python-cli for interface conventions.
---

# Modern CLI recipes

Start from a recipe; each names every file to touch and every test to write. The rules after
them hold for every command, and `reference/` has the reasons and the less common tasks. Interface
rules — exit codes, the stdout/stderr split — are in **python-cli**.

## Recipe: add a command

The scaffold's `about` command (`src/<package>/about.py`, `tests/test_about.py`) is the model. For
a command that calls an API, start from `reference/status.py` instead — the next recipe.

1. **Write `src/<package>/<name>.py`** with three layers, as `about.py` has:
   - plain functions that do the work, taking every dependency (client, clock, paths) as a
     parameter, so a test or a debugger can call them with literal arguments;
   - a renderer: a rich table for `table`, `sys.stdout.write` of JSON for `json`;
   - `<name>_command(ctx: typer.Context, ..., output: OutputOption = None) -> None`, which calls
     `load_settings(verbose=options.verbose, config=options.config, output=output)` with
     `options = global_options(ctx)`, delegates, and raises
     `typer.Exit(1)` on a runtime failure. Nothing else. A positional argument is
     `names: Annotated[list[str], typer.Argument(help="...")]`, with no default; one that must be
     validated or is not a string: "Recipe: a validated argument".
2. **Register it in `src/<package>/cli.py`**, beside `about`:

   ```python
   from .status import status_command
   ...
   app.command("status")(status_command)
   ```

   By reference, never as a nested `typer.Typer`, so the command stays one word.
3. **Write `tests/test_<name>.py`** in two halves, as `test_about.py` has: the plain functions with
   injected dependencies, then end to end through `main([...])`, asserting the exit code, stdout
   (`json.loads` it for `-o json`) and stderr separately.
4. **Check:** `uv run pytest`, then `prek run --all-files`.

## Recipe: call an HTTP API

Copy the vetted client and the worked command rather than writing either from scratch:

```bash
uv add httpx
cp .claude/skills/python-cli-modern/reference/http_client.py src/<package>/
cp .claude/skills/python-cli-modern/reference/test_http_client.py tests/
cp .claude/skills/python-cli-modern/reference/status.py src/<package>/          # optional: a worked command
cp .claude/skills/python-cli-modern/reference/test_status.py tests/
```

They pass the gate and their tests exactly as copied (a generation test proves it). Then rename
`status` to your command and register it as in the first recipe. `build_client()` gives per-phase
timeouts, a User-Agent, retries on 429 and 5xx honouring `Retry-After`, `HTTPS_PROXY` and
`NO_PROXY`, and a debug line per request. An API with a rate policy needs the first retry no
sooner than it allows: `build_client(backoff=1.0)` for one request per second, or `attempts=1` to
never retry. Tests replace the network with `httpx.MockTransport`;
`test_status.py` shows both ways — passing a client to a function, and replacing `build_client`
for a test through `main`.

**Mock what the service really returns.** Before writing a test for a failure — an unknown id, a
bad parameter — provoke it once against the real service (`curl -s -w ' [%{http_code}]\n' URL`)
and mock that status and body. Docs and specs are often wrong about failures: an "absent" key can
be a 404, and the command must handle the one that actually arrives.

Prefer a credible vendor SDK (`boto3`, `google-cloud-*`, `azure-*`, `PyGithub`, `kubernetes`) when
one covers the service: it already handles auth refresh, pagination and retries. Either way, the
client is a parameter with a default, never a module-level singleton.

## Recipe: a validated argument

For any value that is not a plain `str`, `int` or `Path` — an amount, a `BASE/QUOTE` pair, a URL —
parse it in a function typer calls, so a bad value is typer's own usage error (exit 2, "Invalid
value for 'AMOUNT': ...") before the command body runs. `reference/status.py` has `parse_url`.

1. **Write `parse_<thing>(raw: str) -> <Type>`** in the command's module. It returns the parsed
   value or raises `typer.BadParameter` naming the value and the expected form; for a `Decimal`,
   `raise typer.BadParameter(msg) from exc` on `InvalidOperation`.
2. **Declare it**, typed as what the parser returns, with a metavar for the help:

   ```python
   amount: Annotated[Decimal, typer.Argument(parser=parse_amount, metavar="AMOUNT")]
   margin: Annotated[Decimal, typer.Option("--margin", "-m", parser=parse_amount)] = Decimal(0)
   ```

3. **Test both halves**, as `test_status.py` does: the parser directly, with each malformed form
   (`pytest.raises(typer.BadParameter)`), and one bad value through `main`, asserting exit 2,
   empty stdout and the value named on stderr.

Never check the value in the command body and raise `typer.Exit(2)` by hand: typer then prints no
usage line, and the message format differs from every other usage error.

## Recipe: add a setting

A setting resolves flag, then `<PREFIX>_<FIELD>` environment variable, then the `<field>:` key in
the YAML config file, then default. The file needs no edit: every field is read from it. Four
edits, and the wiring tests at the end of `tests/test_config.py` fail, naming the step, until all
are done:

1. **`src/<package>/config.py`** — add the field to `Settings` with a default, *and* to
   `_Overrides`.
2. **Same file** — add a keyword to `load_settings`, `<field>: <type> | None = None`, and copy it
   into `given` when it is not `None`.
3. **`src/<package>/options.py`** — declare the option alias with a `None` default and
   `(env: {env_var('<field>')})` in its help. A boolean needs both halves: `--x/--no-x`.
4. **Put the option on each command that uses it** and pass it to `load_settings`.

Then test the new setting's precedence in `tests/test_config.py`, as the `output` tests there do:
the environment beats the default, and the flag beats the environment. A string setting in YAML
needs quotes when its value looks like another type: an unquoted `no` loads as `false`. Why every option
defaults to `None` and typer's `envvar=` is not used: `reference/configuration.md`.

## Recipe: add a secret setting

A token, password or key. It resolves from `<PREFIX>_<FIELD>` or the config file — **never a
flag**, since a flag's value lands in shell history and in any process listing. One edit:

1. **`src/<package>/config.py`** — add the field to `Settings` as `SecretStr`, usually optional:
   `api_token: SecretStr | None = None`. Not to `_Overrides`, `load_settings` or `options.py`.

`SecretStr` masks it in `about`'s table and JSON and in the `-v` debug log. Unwrap it with
`.get_secret_value()` only at the point of use — where the client is built, or in a command whose
job is to output the secret, whose JSON then carries it raw:

```python
if settings.api_token is None:
    raise SettingsError(f"no API token: set {env_var('api_token')} or the config file")
with build_client() as client:
    client.headers["Authorization"] = f"Bearer {settings.api_token.get_secret_value()}"
```

Send it in a header, never the query string: the client logs every URL at debug. A field ending
`token`, `password`, `secret`, `api_key` or `private_key` that is not `SecretStr` fails
`tests/test_config.py`. Why: `reference/configuration.md`.

## Rules every command follows

- **`Annotated` for every typer parameter**, never `= typer.Option(...)` defaults. `reference/typer.md`.
- **Every command that emits data takes `--output`/`-o`**, declared per command with
  `OutputOption`, not on the callback. The format never changes because stdout is a pipe.
  `reference/output.md`.
- **Data to `out` (stdout), everything else to `err` (stderr)** — the two consoles in `output.py`.
  A progress bar on stdout corrupts the data. `reference/output.md`.
- **Log with loguru, `{}` placeholders**, never `print`. In tests through `main`, assert on
  captured stderr; `caplog` sees nothing. `reference/logging.md`.
- **`main` returns an exit code** through `run_app`; never `sys.exit` below the `__main__` block,
  and never `import click` — typer 0.27 vendors it. `reference/typer.md`.
- **A runtime failure names its cause.** In the `except` that exits, put the exception in the
  stderr message and log it, as `status.py` does: `logger.opt(exception=exc).debug(...)`, then
  `raise typer.Exit(1) from exc`. typer never prints an exit's cause, so `from exc` alone hides it.
- **pydantic `BaseModel` at the edges** (API responses, output shapes), dataclasses inside.
  `reference/models.md`.

The scaffold depends on `typer`, `pydantic`, `pydantic-settings`, `rich` and `loguru`. Add
anything else with `uv add` when the first command needs it: `httpx`, `prompt_toolkit` for prompts,
`SQLModel` for SQL Server.

## References

| File | Read when |
|---|---|
| `reference/status.py`, `reference/test_status.py` | writing a command that calls an API — copy them |
| `reference/http_client.py`, `reference/test_http_client.py` | any HTTP at all — copy them |
| `reference/httpx.md` | testing code that takes a client; pagination; error handling |
| `reference/configuration.md` | a setting behaves unexpectedly, or before changing `config.py` |
| `reference/output.md` | adding an output format, or anything decorative |
| `reference/typer.md` | typer surprises you, or before changing `cli.py` |
| `reference/logging.md` | asserting on logs, or routing a library's logging |
| `reference/concurrency.md` | fanning out over many items (`--concurrency`) |
| `reference/prompts.md` | asking the user anything mid-command |
| `reference/completion.md` | shell completion |
| `reference/models.md` | modelling an API response, or SQLModel |
