# Configuration: flag, then environment variable, then default

The one home for why settings work as they do in `config.py` and `options.py`. Read before adding a
setting in an unusual way, or when a flag or variable does not win when it should.

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

**Secrets** are the one exception to "every setting has a flag":

- **Environment only.** A flag's value is visible in shell history and to anyone who can list
  processes, so a secret field is left out of `_Overrides`, `load_settings` and `options.py`. The
  wiring tests find secret fields with `secret_fields()` and exempt them from those steps.
- **`SecretStr`, so incidental exposure is masked.** Its `repr` is `SecretStr('**********')` and
  `model_dump(mode="json")` gives `'**********'`, so the debug log of the resolved settings and
  `about`'s table and JSON never show it. Discoverability comes from `about`, which still lists
  the field and its variable.
- **Unwrap once, at the point of use.** `.get_secret_value()` where the client is built, or in a
  command that exists to output the secret. Such a command emits it raw, JSON included, as
  `terraform output -json` and `gh auth token` do: there the reveal is the point, and the explicit
  call makes it greppable.
- **Never in a URL.** `http_client.py` logs each request's URL at debug; a header is not logged.

Global options live on `@app.callback()`, which stores what it was given in a frozen
`GlobalOptions` on `ctx.obj`. Each command reads it back with `global_options(ctx)` and calls
`load_settings` once with its own flags added, so settings are validated in one place and the
command body sees a single typed `Settings`, never a raw `ctx.obj`.

Do not merge a command's overrides into existing settings with `model_copy(update=...)` — it skips
validation entirely. Construct a new `Settings`.
