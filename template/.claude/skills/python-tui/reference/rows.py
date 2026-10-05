"""The logic behind the `browse` command: read a CSV file, and filter its rows. No Textual here.

    cp .claude/skills/python-tui/reference/rows.py src/<package>/
    cp .claude/skills/python-tui/reference/test_rows.py tests/

Everything the screen shows is computed by plain functions in this module, so a test calls them
with literal arguments and never starts an app, and a debugger can step through them — which it
cannot do inside a running TUI.
"""

import csv
import dataclasses
from collections.abc import Iterable
from pathlib import Path

type Row = tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class RowTable:
    """A CSV file's header and rows, every row as wide as the header."""

    headers: Row
    rows: tuple[Row, ...]


def read_rows(path: Path) -> RowTable:
    """Read the CSV file at `path`, refusing one with no header or with a ragged row."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        headers = tuple(next(reader, ()))
        rows = tuple(tuple(row) for row in reader)
    if not headers:
        msg = f"{path} is empty; expected a header row, then one line per row"
        raise ValueError(msg)
    for number, row in enumerate(rows, start=2):
        if len(row) != len(headers):
            msg = f"{path}, line {number}: {len(row)} cells, but the header has {len(headers)}"
            raise ValueError(msg)
    return RowTable(headers=headers, rows=rows)


def _row_matches(row: Row, needle: str) -> bool:
    """Return whether any cell of `row` contains `needle`, which is already case-folded."""
    return any(needle in cell.casefold() for cell in row)


def matching_rows(rows: Iterable[Row], query: str) -> list[Row]:
    """Return the rows with a cell containing `query`, ignoring case. A blank query matches all."""
    needle = query.strip().casefold()
    return [row for row in rows if _row_matches(row, needle)]
