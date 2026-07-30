"""Look up GPS coordinates for a place using OpenStreetMap's Nominatim API.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires a descriptive User-Agent — the default httpx one is rejected with HTTP 403
— and caps callers at one request per second. Every subcommand here issues at most
one request, so no client-side throttling is needed.
"""

import argparse
import dataclasses
import json
import logging
import sys

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "claude-geo-cli (https://github.com/tboss-dev)"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_LIMIT = 10


@dataclasses.dataclass(frozen=True)
class Place:
    """A single Nominatim search result."""

    display_name: str
    latitude: float
    longitude: float
    place_type: str


def _parse_place(raw: dict[str, str]) -> Place:
    """Convert one Nominatim result object into a `Place`."""
    return Place(
        display_name=raw["display_name"],
        latitude=float(raw["lat"]),
        longitude=float(raw["lon"]),
        place_type=raw.get("type", "unknown"),
    )


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
    return [_parse_place(raw) for raw in response.json()]


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


def format_places(places: list[Place], *, as_json: bool = False) -> str:
    """Render `places` for stdout, as a JSON array or one line per match."""
    if as_json:
        return json.dumps([dataclasses.asdict(place) for place in places])
    lines = [
        f"{place.latitude:.6f}, {place.longitude:.6f}  ({place.place_type})  {place.display_name}"
        for place in places
    ]
    return "\n".join(lines)


def handle_get_coordinates(args: argparse.Namespace) -> int:
    """Unpack argv and delegate. Returns an exit code."""
    return get_coordinates(
        query=" ".join(args.location),
        limit=args.limit,
        timeout=args.timeout,
        as_json=args.json,
    )


def get_coordinates(query: str, limit: int, timeout: float, *, as_json: bool) -> int:
    """Look up `query`, print the matches, and return an exit code."""
    logger.debug("querying Nominatim for %r with limit=%d", query, limit)
    try:
        places = find_coordinates(query, limit=limit, timeout=timeout)
    except httpx.HTTPError:
        logger.exception("could not reach %s", NOMINATIM_URL)
        return 1

    if not places:
        logger.error("no matches for %r", query)
        return 1

    sys.stdout.write(f"{format_places(places, as_json=as_json)}\n")
    return 0


def _add_get_coordinates_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `get-coordinates` subcommand."""
    parser = subparsers.add_parser(
        "get-coordinates",
        help="look up GPS coordinates for a town, village or city",
    )
    parser.add_argument(
        "location",
        nargs="+",
        help="free-text place name, e.g. cleve or 'cleve, south australia'",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="maximum number of matches to return",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="request timeout in seconds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON array instead of one line per match",
    )
    parser.set_defaults(handler=handle_get_coordinates)


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="geo",
        description="Look up geographic data via OpenStreetMap's Nominatim API.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log request details to stderr",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_get_coordinates_command(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
