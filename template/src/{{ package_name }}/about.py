"""The `about` command: what this tool is, and the configuration it resolved.

A placeholder to replace or build beside. It is deliberately small, but it passes through every
layer a real command does: a global flag from the app callback, a command flag, both overridable
from the environment, settings validated once, logging on stderr, and table or JSON on stdout.

The work and the typer wiring are separate. `collect_about` and `emit_about` are plain functions
you can call with literal arguments from a test, from pdb or from a debugger's evaluate prompt;
`about_command` only unpacks flags and delegates.
"""

import platform
import sys
from collections.abc import Callable
from importlib import metadata

import typer
from loguru import logger
from pydantic import BaseModel
from rich.table import Table

from .config import DIST_NAME, PROG_NAME, Settings, env_var, load_settings
from .options import OutputOption, global_options
from .output import OutputFormat, out


class About(BaseModel):
    """What `about` reports. Also the shape of its JSON output."""

    name: str
    version: str
    python: str
    platform: str
    settings: Settings


def collect_about(
    settings: Settings,
    *,
    version_of: Callable[[str], str] = metadata.version,
    python_version: Callable[[], str] = platform.python_version,
    platform_name: Callable[[], str] = platform.platform,
) -> About:
    """Gather the facts `about` reports. Pass the callables to pin them in a test."""
    return About(
        name=PROG_NAME,
        version=version_of(DIST_NAME),
        python=python_version(),
        platform=platform_name(),
        settings=settings,
    )


def build_about_table(about: About) -> Table:
    """Return a two-column table, one row per fact and one per setting."""
    table = Table(show_header=False)
    # Fold rather than truncate: a variable name or a config path cut to "…" cannot be copied.
    table.add_column("Key", style="bold", overflow="fold")
    table.add_column("Value", overflow="fold")
    table.add_row("Name", about.name)
    table.add_row("Version", about.version)
    table.add_row("Python", about.python)
    table.add_row("Platform", about.platform)
    for field, value in about.settings.model_dump(mode="json").items():
        table.add_row(f"{field} ({env_var(field)})", str(value))
    return table


def emit_about(about: About, fmt: OutputFormat) -> None:
    """Write `about` to stdout in the requested format.

    JSON is written directly rather than through rich, so no console setting can break it.
    """
    if fmt is OutputFormat.json:
        sys.stdout.write(about.model_dump_json() + "\n")
        return
    out.print(build_about_table(about))


def about_command(ctx: typer.Context, output: OutputOption = None) -> None:
    """Show this tool's version, runtime and resolved configuration."""
    settings = load_settings(global_options(ctx), output=output)
    logger.debug("resolved {!r}", settings)
    emit_about(collect_about(settings), settings.output)
