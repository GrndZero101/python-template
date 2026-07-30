"""Report the current user and hostname.

Exit codes: 0 on success, 1 if the identity cannot be determined, 2 on usage error.
"""

import getpass
import json
import socket
import sys
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

import typer
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

from claude.logging_setup import configure_logging
from claude.typer_entrypoint import run_app

out = Console()  # data only — stdout

app = typer.Typer(add_completion=False, no_args_is_help=False)


class OutputFormat(StrEnum):
    """How to render the command result."""

    text = "text"
    json = "json"


class Identity(BaseModel):
    """Who this process is running as, and where."""

    user: str
    host: str


def current_identity(
    get_user: Callable[[], str] = getpass.getuser,
    get_host: Callable[[], str] = socket.gethostname,
) -> Identity:
    """Return the current user and hostname.

    Both lookups are injected so tests can pin them without touching the
    environment, and so either can be substituted from a breakpoint.
    """
    return Identity(user=get_user(), host=get_host())


def render_identity(identity: Identity, fmt: OutputFormat) -> str:
    """Render `identity` as `user@host` text or as a JSON object."""
    if fmt is OutputFormat.json:
        return json.dumps(identity.model_dump())
    return f"{identity.user}@{identity.host}"


def emit(identity: Identity, fmt: OutputFormat) -> None:
    """Write `identity` to stdout in the requested format."""
    rendered = render_identity(identity, fmt)
    if fmt is OutputFormat.json:
        sys.stdout.write(rendered + "\n")
        return
    out.print(rendered)


OutputOption = Annotated[
    OutputFormat, typer.Option("--output", "-o", envvar="WHOAMI_OUTPUT", help="output format")
]


@app.command()
def whoami(
    output: OutputOption = OutputFormat.text,
    *,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="log details to stderr")] = False,
) -> None:
    """Print the current user and hostname."""
    configure_logging(verbose=verbose)
    try:
        identity = current_identity()
    except OSError:
        logger.exception("could not determine the current user or hostname")
        raise typer.Exit(1) from None

    logger.debug("resolved user={} host={}", identity.user, identity.host)
    emit(identity, output)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    return run_app(app, argv, prog_name="whoami")


if __name__ == "__main__":
    sys.exit(main())
