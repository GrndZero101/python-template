# Configuration: flag, then environment variable, then config file, then default

The one home for why settings work as they do in `config.py` and `options.py`. Read before adding a
setting in an unusual way, or when a flag or variable does not win when it should.

Every setting resolves in that order, and `pydantic-settings` does the merge — never hand-roll it.
The config file is the subject of its own section below.
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

- **Never a flag.** A flag's value is visible in shell history and to anyone who can list
  processes, so a secret field is left out of `_Overrides`, `load_settings` and `options.py`; it
  comes from its variable or the config file. The wiring tests find secret fields with
  `secret_fields()` and exempt them from those steps. A validation error masks its value.
- **`SecretStr`, so incidental exposure is masked.** Its `repr` is `SecretStr('**********')` and
  `model_dump(mode="json")` gives `'**********'`, so the debug log of the resolved settings and
  `about`'s table and JSON never show it. Discoverability comes from `about`, which still lists
  the field and its variable.
- **Unwrap once, at the point of use.** `.get_secret_value()` where the client is built, or in a
  command that exists to output the secret. Such a command emits it raw, JSON included, as
  `terraform output -json` and `gh auth token` do: there the reveal is the point, and the explicit
  call makes it greppable.
- **Never in a URL.** `http_client.py` logs each request's URL at debug; a header is not logged.

**The config file** (`config_file.py`) holds a user's standing preferences, below the
environment so a variable can still override it for one run:

- **YAML, keyed by field name**, parsed with `yaml.safe_load` by `ConfigFileSource`, which hands
  the raw values to pydantic, so one validation pass covers every layer. Not pydantic-settings'
  `YamlConfigSettingsSource`: it cannot take a path chosen at run time, and a file holding a list
  escapes it as a bare `ValueError`. PyYAML is YAML 1.1: an unquoted
  `no`, `off` or `yes` is a boolean. A field typed `str` rejects it rather than storing `"False"`,
  but the fix is quoting, so say so in any example a user copies.
- **Unknown keys are an error naming the file**, as `extra="forbid"` makes them for the other
  sources. A typo in a config file must not be silently ignored.
- **`config` is itself a setting**: `--config` beats `<PREFIX>CONFIG`, which beats the default
  location. `ConfigFileSource` runs after the init and environment sources and reads the resolved
  value from `current_state`; the file cannot name itself. A file named this way must exist; the
  default need not, and `about` shows which path is in use.
- **The default location is where CLI users look**: `$XDG_CONFIG_HOME/<script>/config.yaml` when
  that is set and absolute, on every platform; otherwise `~/.config/<script>/config.yaml`, macOS
  included, rather than `~/Library/Application Support`; and `%APPDATA%` on Windows, the roaming
  profile, because settings should follow the user.
- **Tests never read the developer's file.** `conftest.py` points `XDG_CONFIG_HOME` into
  `tmp_path` for every test; a test that needs a file writes one there, or passes `--config`.
- **No project-local file** (`./<script>.yaml`). It would make the working directory change a
  command's behaviour, which is the surprise the `.env` default avoids.

Global options live on `@app.callback()`, which stores what it was given in a frozen
`GlobalOptions` on `ctx.obj`. Each command reads it back with `global_options(ctx)` and calls
`load_settings` once with its own flags added, so settings are validated in one place and the
command body sees a single typed `Settings`, never a raw `ctx.obj`.

Do not merge a command's overrides into existing settings with `model_copy(update=...)` — it skips
validation entirely. Construct a new `Settings`.
