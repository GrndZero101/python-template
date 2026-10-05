"""The `browse` command: a CSV file as a full-screen table, filtered as you type. A worked TUI command.

    uv add textual
    uv add --dev pytest-asyncio textual-dev
    cp .claude/skills/python-tui/reference/browse.py src/<package>/
    cp .claude/skills/python-tui/reference/test_browse.py tests/
    # with rows.py and test_rows.py, and register it in cli.py — see the python-tui skill

The app only displays: `rows.py` reads and filters, and every handler here unpacks its event and
delegates there. `browse_command` reads the file before the app starts, so a bad file is an
ordinary error on stderr rather than a broken screen.
"""

import sys
from pathlib import Path
from typing import Annotated, ClassVar

import typer
from loguru import logger
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Footer, Input

from .rows import Row, RowTable, matching_rows, read_rows

RUNTIME_FAILURE = 1


class BrowseApp(App[None]):
    """A full-screen table of `source`'s rows, narrowed by whatever is typed in the filter box."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "clear_filter", "Clear filter"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, source: RowTable) -> None:
        """Show `source`; nothing is read or computed until the app mounts."""
        super().__init__()
        self.source = source

    def compose(self) -> ComposeResult:
        """Lay out the filter box above the table."""
        yield Input(placeholder="Type to filter rows")
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        """Add the columns, then every row."""
        self.query_one(DataTable).add_columns(*self.source.headers)
        self.show_rows(self.source.rows)

    @on(Input.Changed)
    def filter_changed(self, event: Input.Changed) -> None:
        """Re-filter on every keystroke."""
        self.show_rows(matching_rows(self.source.rows, event.value))

    def action_clear_filter(self) -> None:
        """Empty the filter box, which shows every row again."""
        self.query_one(Input).value = ""

    def show_rows(self, rows: tuple[Row, ...] | list[Row]) -> None:
        """Replace the table's rows, keeping its columns."""
        table = self.query_one(DataTable)
        table.clear()
        table.add_rows(rows)


def parse_csv_path(raw: str) -> Path:
    """Return `raw` as a path if it is an existing .csv file. typer calls this."""
    path = Path(raw)
    if path.suffix.lower() != ".csv":
        msg = f"expected a .csv file, got {raw!r}"
        raise typer.BadParameter(msg)
    if not path.is_file():
        msg = f"{raw!r} does not exist or is not a file"
        raise typer.BadParameter(msg)
    return path


def browse_command(
    path: Annotated[
        Path,
        typer.Argument(
            parser=parse_csv_path, metavar="FILE", help="A .csv file with a header row."
        ),
    ],
) -> None:
    """Browse a CSV file as a table, filtering rows as you type. Escape clears; ctrl+q quits."""
    try:
        source = read_rows(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        logger.opt(exception=exc).debug("could not read {}", path)
        sys.stderr.write(f"Error: could not read {path}: {exc}\n")
        raise typer.Exit(RUNTIME_FAILURE) from exc
    logger.debug("browsing {} rows from {}", len(source.rows), path)
    BrowseApp(source).run()
