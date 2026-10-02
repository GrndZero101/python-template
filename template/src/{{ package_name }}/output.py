"""Shared output plumbing for every subcommand: the output formats and the two consoles.

Data goes to `out` (stdout); anything decorative or human-facing goes to `err` (stderr). The
format changes only when the caller asks, never because stdout is a pipe.

Why two consoles, and why the format never changes on its own: .claude/skills/python-cli-modern/reference/output.md.
"""

from enum import StrEnum

from rich.console import Console

out = Console()  # data only — stdout
err = Console(stderr=True)  # progress, status, human-facing errors


class OutputFormat(StrEnum):
    """How to render a command result."""

    table = "table"
    json = "json"
