"""Look up geographic data using OpenStreetMap's Nominatim API.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires a descriptive User-Agent — the default httpx one is rejected with HTTP 403
— and caps callers at one request per second. Every subcommand here issues at most
one request, so no client-side throttling is needed.
"""

import json
import sys
from typing import Annotated

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, Field
from rich.table import Table

from claude.logging_setup import configure_logging
from claude.output import OutputFormat, OutputOption, out

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "claude-geo-cli (https://github.com/tboss-dev)"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_LIMIT = 10


class Place(BaseModel):
    """A single Nominatim search result."""

    display_name: str
    latitude: float = Field(validation_alias="lat")
    longitude: float = Field(validation_alias="lon")
    place_type: str = Field(validation_alias="type", default="unknown")


def _request_places(
    client: httpx.Client,
    query: str,
    limit: int,
    timeout: float,
) -> list[Place]:
    """Fetch and parse search results using an already-open client."""
    response = client.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": limit},
        timeout=timeout,
    )
    response.raise_for_status()
    return [Place.model_validate(raw) for raw in response.json()]


def find_coordinates(
    query: str,
    limit: int = DEFAULT_LIMIT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> list[Place]:
    """Return every place Nominatim matches against `query`.

    Pass `client` to reuse a connection or to substitute a transport in tests;
    when omitted, a client carrying the required User-Agent is opened and closed
    around the single request.
    """
    if client is not None:
        return _request_places(client, query, limit, timeout)
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as owned_client:
        return _request_places(owned_client, query, limit, timeout)


def render_places_json(places: list[Place]) -> str:
    """Render `places` as a JSON array."""
    return json.dumps([place.model_dump() for place in places])


def _build_places_table(places: list[Place]) -> Table:
    """Return a rich Table with one row per place."""
    table = Table()
    table.add_column("Latitude", justify="right")
    table.add_column("Longitude", justify="right")
    table.add_column("Type")
    table.add_column("Name")
    for place in places:
        table.add_row(
            f"{place.latitude:.6f}",
            f"{place.longitude:.6f}",
            place.place_type,
            place.display_name,
        )
    return table


def emit(places: list[Place], fmt: OutputFormat) -> None:
    """Write `places` to stdout in the requested format."""
    if fmt is OutputFormat.json:
        sys.stdout.write(render_places_json(places) + "\n")
        return
    out.print(_build_places_table(places))


def geo(
    location: Annotated[
        list[str],
        typer.Argument(help="free-text place name, e.g. cleve or 'cleve, south australia'"),
    ],
    output: OutputOption = OutputFormat.table,
    limit: Annotated[int, typer.Option(help="maximum number of matches to return")] = DEFAULT_LIMIT,
    timeout: Annotated[
        float, typer.Option(help="request timeout in seconds")
    ] = DEFAULT_TIMEOUT_SECONDS,
    *,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="log request details to stderr")
    ] = (False),
) -> None:
    """Look up GPS coordinates for a town, village or city."""
    configure_logging(verbose=verbose)
    query = " ".join(location)
    logger.debug("querying Nominatim for {!r} with limit={}", query, limit)
    try:
        places = find_coordinates(query, limit=limit, timeout=timeout)
    except httpx.HTTPError:
        logger.exception("could not reach {}", NOMINATIM_URL)
        raise typer.Exit(1) from None

    if not places:
        logger.error("no matches for {!r}", query)
        raise typer.Exit(1)

    emit(places, output)
