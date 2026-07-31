"""Shared output plumbing for every subcommand.

Two consoles, deliberately. `rich.Console()` writes to **stdout** by default, and so do
`Progress` and `status`, so a stray `console.print("Fetching…")` would corrupt the stream a
caller is parsing. Data goes to `out`; anything decorative or human-facing goes to `err`.

The `--output` default never changes on its own. `table` on a terminal, `table` in a pipe.
rich suppresses colour by itself when stdout is not a tty, but the *data format* only changes
when the caller asks — via `-o json` or `CLI_OUTPUT=json`. A tool that silently emits JSON when
redirected behaves differently in CI than in the terminal it was tested in, and that divergence
is invisible until it matters.
"""

from enum import StrEnum
from typing import Annotated

import typer
from rich.console import Console

out = Console()  # data only — stdout
err = Console(stderr=True)  # progress, status, human-facing errors


class OutputFormat(StrEnum):
    """How to render a command result."""

    table = "table"
    json = "json"


OutputOption = Annotated[
    OutputFormat,
    typer.Option("--output", "-o", envvar="CLI_OUTPUT", help="output format"),
]
