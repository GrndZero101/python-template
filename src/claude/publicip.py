"""Report this machine's public IP address as seen from the internet.

Uses https://checkip.amazonaws.com, which answers with the caller's address as a
bare line of text.
"""

import argparse
import ipaddress
import logging
import sys

import httpx

logger = logging.getLogger(__name__)

CHECKIP_URL = "https://checkip.amazonaws.com"
DEFAULT_TIMEOUT_SECONDS = 5.0


def parse_ip(raw: str, source: str = CHECKIP_URL) -> str:
    """Validate `raw` as an IP address and return it normalised."""
    candidate = raw.strip()
    if not candidate:
        msg = f"{source} returned an empty body; expected a single IP address"
        raise ValueError(msg)
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as exc:
        msg = f"{source} returned {candidate!r}, which is not a valid IP address"
        raise ValueError(msg) from exc


def _request_ip(client: httpx.Client, url: str, timeout: float) -> str:
    """Fetch and validate the address using an already-open client."""
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    return parse_ip(response.text, source=url)


def fetch_public_ip(
    url: str = CHECKIP_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> str:
    """Return this machine's public IP address.

    Pass `client` to reuse a connection or to substitute a transport in tests;
    when omitted, a client is created and closed around the single request.
    """
    if client is not None:
        return _request_ip(client, url, timeout)
    with httpx.Client() as owned_client:
        return _request_ip(owned_client, url, timeout)


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="publicip",
        description="Print this machine's public IP address.",
    )
    parser.add_argument("--url", default=CHECKIP_URL, help="service to query")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="request timeout in seconds",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log request details to stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    logger.debug("querying %s with a %.1fs timeout", args.url, args.timeout)
    try:
        address = fetch_public_ip(url=args.url, timeout=args.timeout)
    except httpx.HTTPError:
        logger.exception("could not reach %s", args.url)
        return 1
    except ValueError:
        logger.exception("unexpected response from %s", args.url)
        return 1

    # stdout is data so the address stays pipeable; diagnostics went to stderr.
    sys.stdout.write(f"{address}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
