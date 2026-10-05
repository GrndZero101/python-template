"""The `summary` command: requests, server errors and p95 duration per service. A worked data command.

    uv add polars
    cp .claude/skills/python-data/reference/summary.py src/<package>/
    cp .claude/skills/python-data/reference/test_summary.py tests/
    # and register it in cli.py — see "Recipe: add a data command" in the python-data skill

It reads a CSV or parquet file of request records — `service`, `status`, `duration_ms` — and has
the shape every command here has:

- `parse_records_path` validates the argument as typer parses it: a missing file or another format
  is a usage error, exit 2, before any work starts.
- `scan_records` reads lazily with the schema fixed, never inferred. `summarize` is the pipeline:
  each stage a name, collected once. Both are plain functions over polars frames, so a test passes
  a five-row frame and a debugger can call them with literal arguments.
- `build_summary_table` and `emit_summary` render; JSON is written straight to stdout.
- `summary_command` only resolves settings, delegates and turns a bad file into exit 1.
"""

import sys
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from rich.table import Table

from .config import load_settings
from .options import OutputOption, global_options
from .output import OutputFormat, err, out

RUNTIME_FAILURE = 1
FIRST_SERVER_ERROR = 500
SUFFIXES = (".csv", ".parquet")
# The input's shape, declared rather than inferred: inference reads a sample, so one file's integer
# column can be another's float, silently.
RECORD_SCHEMA = pl.Schema({"service": pl.String, "status": pl.Int64, "duration_ms": pl.Float64})
# The output's shape. A test asserts it, which catches the dtype drift a value comparison misses.
SUMMARY_SCHEMA = pl.Schema({
    "service": pl.String,
    "requests": pl.UInt32,
    "errors": pl.UInt32,
    "p95_ms": pl.Float64,
})


def parse_records_path(raw: str) -> Path:
    """Return `raw` as a path if it is an existing .csv or .parquet file. typer calls this."""
    path = Path(raw)
    if path.suffix.lower() not in SUFFIXES:
        msg = f"expected a .csv or .parquet file, got {raw!r}"
        raise typer.BadParameter(msg)
    if not path.is_file():
        msg = f"{raw!r} does not exist or is not a file"
        raise typer.BadParameter(msg)
    return path


def scan_records(path: Path) -> pl.LazyFrame:
    """Scan the records in `path` lazily. Nothing is read until the result is collected."""
    if path.suffix.lower() == ".csv":
        return pl.scan_csv(path, schema=RECORD_SCHEMA)
    return pl.scan_parquet(path, schema=RECORD_SCHEMA)


def summarize(records: pl.LazyFrame) -> pl.DataFrame:
    """Return one row per service, in service order: requests, 5xx responses and p95 duration.

    Each stage is a name, so a breakpoint can inspect any of them with `.head().collect()`.
    """
    server_errors = (pl.col("status") >= FIRST_SERVER_ERROR).sum()
    p95 = pl.col("duration_ms").quantile(0.95, interpolation="nearest")
    per_service = records.group_by("service").agg(
        pl.len().alias("requests"),
        server_errors.alias("errors"),
        p95.alias("p95_ms"),
    )
    ordered = per_service.sort("service")  # group_by's order is not guaranteed
    return ordered.collect()


def build_summary_table(summary: pl.DataFrame) -> Table:
    """Return one row per service, numbers right-aligned."""
    table = Table()
    table.add_column("Service")
    table.add_column("Requests", justify="right")
    table.add_column("5xx", justify="right")
    table.add_column("p95 ms", justify="right")
    for service, requests, errors, p95_ms in summary.iter_rows():
        table.add_row(service, str(requests), str(errors), f"{p95_ms:.1f}")
    return table


def emit_summary(summary: pl.DataFrame, fmt: OutputFormat) -> None:
    """Write the summary to stdout: one JSON array of objects, or a table."""
    if fmt is OutputFormat.json:
        sys.stdout.write(f"{summary.write_json()}\n")
        return
    out.print(build_summary_table(summary))


def summary_command(
    ctx: typer.Context,
    records: Annotated[
        Path,
        typer.Argument(
            parser=parse_records_path,
            metavar="FILE",
            help="A .csv or .parquet file with service, status and duration_ms columns.",
        ),
    ],
    output: OutputOption = None,
) -> None:
    """Summarize request records per service: requests, server errors and p95 duration."""
    settings = load_settings(global_options(ctx), output=output)
    try:
        summary = summarize(scan_records(records))
    except pl.exceptions.PolarsError as exc:
        logger.opt(exception=exc).debug("could not summarize {}", records)
        err.print(f"Error: could not summarize {records}: {exc}")
        raise typer.Exit(RUNTIME_FAILURE) from exc
    emit_summary(summary, settings.output)
