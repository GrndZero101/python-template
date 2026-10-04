"""Typer glue between command-line flags and `Settings`.

Every option that maps to a setting defaults to `None`, meaning "not given", and names its
environment variable in its help as `(env: NAME)`, built with `env_var`. Global options
(`--verbose`, `--config`, `--version`) live on the app callback and go before the command; the
callback stores them in a `GlobalOptions`, which each command reads back with
`global_options(ctx)`.

Why `None`, why not typer's `envvar=`, and why not `[env var: NAME]`: .claude/skills/python-cli-modern/reference/configuration.md.
"""

import dataclasses
import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer

from .config import DIST_NAME, PROG_NAME, env_var
from .output import OutputFormat


@dataclasses.dataclass(frozen=True)
class GlobalOptions:
    """The global flags as given on the command line; `None` means not given."""

    verbose: bool | None = None
    config: Path | None = None


def global_options(ctx: typer.Context) -> GlobalOptions:
    """Return the global flags the app callback stored on `ctx`."""
    if isinstance(ctx.obj, GlobalOptions):
        return ctx.obj
    msg = f"no global options on the context (got {ctx.obj!r}); register commands on cli.app"
    raise TypeError(msg)


def show_version(*, value: bool) -> None:
    """Print the installed version and stop, when `--version` was given."""
    if not value:
        return
    sys.stdout.write(f"{PROG_NAME} {metadata.version(DIST_NAME)}\n")
    raise typer.Exit


VerboseOption = Annotated[
    bool | None,
    typer.Option(
        "--verbose/--no-verbose",
        "-v",
        help=f"Log debug detail to stderr. (env: {env_var('verbose')})",
        show_default=False,
    ),
]

ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help=f"Read settings from this YAML file. (env: {env_var('config')})",
        show_default=False,
    ),
]

VersionOption = Annotated[
    bool,
    typer.Option(
        "--version",
        callback=show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
]

OutputOption = Annotated[
    OutputFormat | None,
    typer.Option(
        "--output",
        "-o",
        help=f"Output format, table by default. (env: {env_var('output')})",
        show_default=False,
    ),
]
