"""Typer glue between command-line flags and `Settings`.

Every option that maps to a setting defaults to `None`, meaning "not given on the command line",
so `load_settings` can tell an absent flag from an explicit one and let the environment through.
A typer default of `False` or `table` would be indistinguishable from the user typing it, and the
environment variable could then never win.

The help text names each environment variable, built from `env_var` so it cannot drift from the
name `Settings` actually reads. It is written `(env: NAME)` rather than typer's own
`[env var: NAME]`, because typer renders help as rich markup and a square-bracketed phrase is
taken for a style tag and silently dropped.

typer's own `envvar=` is deliberately not used: it would parse the variable a second time, with
click's rules rather than pydantic's, and the two could disagree.

Global options (`--verbose`, `--version`) live on the app callback and go *before* the command.
The callback stores what it was given in a `GlobalOptions` on the typer context, and each command
reads it back with `global_options(ctx)` to resolve its own settings.
"""

import dataclasses
import sys
from importlib import metadata
from typing import Annotated

import typer

from .config import DIST_NAME, PROG_NAME, env_var
from .output import OutputFormat


@dataclasses.dataclass(frozen=True)
class GlobalOptions:
    """The global flags as given on the command line; `None` means not given."""

    verbose: bool | None = None


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
