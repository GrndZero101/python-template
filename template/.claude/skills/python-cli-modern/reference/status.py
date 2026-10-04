"""The `status` command: check that URLs answer, as a table or as JSON. A worked "add a command".

    cp .claude/skills/python-cli-modern/reference/status.py src/<package>/
    cp .claude/skills/python-cli-modern/reference/test_status.py tests/
    # and register it in cli.py — see "Add a command" in SKILL.md

It has the shape every command here should have, the same as the scaffold's `about`:

- `parse_url` validates each argument as typer parses it: a bad one is a usage error, exit 2,
  through typer's own message, before any work starts.
- `probe` and `probe_all` do the work. They take the client as a parameter, so a test passes one
  backed by `httpx.MockTransport`, and a debugger can call them with literal arguments.
- `build_status_table` and `emit_status` render; JSON is written straight to stdout.
- `status_command` only resolves settings, builds the client, delegates and picks the exit code.

A URL that cannot be reached is part of the result, not a crash: the table says so and the
command exits 1, so `tool status ... && deploy` stops.
"""

import sys
from typing import Annotated

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, TypeAdapter
from rich.table import Table

from .config import load_settings
from .http_client import build_client
from .options import OutputOption, global_options
from .output import OutputFormat, out

FIRST_ERROR_STATUS = 400
RUNTIME_FAILURE = 1
URL_SCHEMES = ("http://", "https://")


class Probe(BaseModel):
    """One URL's result. Also the shape of each object in the JSON output."""

    url: str
    status: int | None
    ok: bool
    error: str | None = None


def parse_url(raw: str) -> str:
    """Return `raw` if it is an http(s) URL. typer calls this for each URL argument.

    `typer.BadParameter` is a usage error: typer prints "Invalid value for 'URL': ..." after the
    usage line and exits 2. Any other exception here would be a crash, not a usage error.
    """
    if not raw.startswith(URL_SCHEMES):
        msg = f"expected an http:// or https:// URL, got {raw!r}"
        raise typer.BadParameter(msg)
    return raw


def probe(client: httpx.Client, url: str) -> Probe:
    """Request `url` once and report what came back, including a failure to connect."""
    try:
        response = client.get(url)
    except httpx.TransportError as exc:
        logger.opt(exception=exc).debug("{} could not be reached", url)
        return Probe(url=url, status=None, ok=False, error=f"{type(exc).__name__}: {exc}")
    return Probe(url=url, status=response.status_code, ok=response.status_code < FIRST_ERROR_STATUS)


def probe_all(client: httpx.Client, urls: list[str]) -> list[Probe]:
    """Probe each URL in turn. Sequential on purpose: see the concurrency reference to fan out."""
    results: list[Probe] = []
    for url in urls:
        results.append(probe(client, url))  # noqa: PERF401 — one breakpoint per URL
    return results


def build_status_table(probes: list[Probe]) -> Table:
    """Return one row per URL."""
    table = Table()
    table.add_column("URL")
    table.add_column("Status", justify="right")
    table.add_column("Result")
    for result in probes:
        status = "-" if result.status is None else str(result.status)
        verdict = "ok" if result.ok else (result.error or "failed")
        table.add_row(result.url, status, verdict)
    return table


def emit_status(probes: list[Probe], fmt: OutputFormat) -> None:
    """Write the results to stdout: one JSON array, or a table."""
    if fmt is OutputFormat.json:
        payload = TypeAdapter(list[Probe]).dump_json(probes).decode()
        sys.stdout.write(f"{payload}\n")
        return
    out.print(build_status_table(probes))


def status_command(
    ctx: typer.Context,
    urls: Annotated[
        list[str],
        typer.Argument(parser=parse_url, metavar="URL", help="One or more URLs to check."),
    ],
    output: OutputOption = None,
) -> None:
    """Check that each URL answers without an error status."""
    options = global_options(ctx)
    settings = load_settings(verbose=options.verbose, config=options.config, output=output)
    with build_client() as client:
        probes = probe_all(client, urls)
    emit_status(probes, settings.output)
    if not all(result.ok for result in probes):
        raise typer.Exit(RUNTIME_FAILURE)
