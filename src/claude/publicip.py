"""Report this machine's public IP address as seen from the internet.

Uses https://checkip.amazonaws.com, which answers with the caller's address as a
bare line of text.
"""

import ipaddress
import sys
from enum import StrEnum
from typing import Annotated

import httpx
import typer
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

from claude.logging_setup import configure_logging
from claude.typer_entrypoint import run_app

out = Console()  # data only — stdout

app = typer.Typer(add_completion=False, no_args_is_help=False)

CHECKIP_URL = "https://checkip.amazonaws.com"
DEFAULT_TIMEOUT_SECONDS = 5.0


class OutputFormat(StrEnum):
    """How to render the command result."""

    text = "text"
    json = "json"


class PublicIp(BaseModel):
    """A validated public IP address."""

    address: str


def parse_ip(raw: str, source: str = CHECKIP_URL) -> PublicIp:
    """Validate `raw` as an IP address and return it normalised."""
    candidate = raw.strip()
    if not candidate:
        msg = f"{source} returned an empty body; expected a single IP address"
        raise ValueError(msg)
    try:
        return PublicIp(address=str(ipaddress.ip_address(candidate)))
    except ValueError as exc:
        msg = f"{source} returned {candidate!r}, which is not a valid IP address"
        raise ValueError(msg) from exc


def _request_ip(client: httpx.Client, url: str, timeout: float) -> PublicIp:
    """Fetch and validate the address using an already-open client."""
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    return parse_ip(response.text, source=url)


def fetch_public_ip(
    url: str = CHECKIP_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> PublicIp:
    """Return this machine's public IP address.

    Pass `client` to reuse a connection or to substitute a transport in tests;
    when omitted, a client is created and closed around the single request.
    """
    if client is not None:
        return _request_ip(client, url, timeout)
    with httpx.Client() as owned_client:
        return _request_ip(owned_client, url, timeout)


def render_public_ip(ip: PublicIp, fmt: OutputFormat) -> str:
    """Render `ip` as bare text or as a JSON object."""
    if fmt is OutputFormat.json:
        return ip.model_dump_json()
    return ip.address


def emit(ip: PublicIp, fmt: OutputFormat) -> None:
    """Write `ip` to stdout in the requested format."""
    rendered = render_public_ip(ip, fmt)
    if fmt is OutputFormat.json:
        sys.stdout.write(rendered + "\n")
        return
    out.print(rendered)


OutputOption = Annotated[
    OutputFormat, typer.Option("--output", "-o", envvar="PUBLICIP_OUTPUT", help="output format")
]


@app.command()
def publicip(
    output: OutputOption = OutputFormat.text,
    url: Annotated[str, typer.Option(help="service to query")] = CHECKIP_URL,
    timeout: Annotated[
        float, typer.Option(help="request timeout in seconds")
    ] = DEFAULT_TIMEOUT_SECONDS,
    *,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="log request details to stderr")
    ] = False,
) -> None:
    """Print this machine's public IP address."""
    configure_logging(verbose=verbose)
    logger.debug("querying {} with a {:.1f}s timeout", url, timeout)
    try:
        ip = fetch_public_ip(url=url, timeout=timeout)
    except httpx.HTTPError:
        logger.exception("could not reach {}", url)
        raise typer.Exit(1) from None
    except ValueError:
        logger.exception("unexpected response from {}", url)
        raise typer.Exit(1) from None

    emit(ip, output)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    return run_app(app, argv, prog_name="publicip")


if __name__ == "__main__":
    sys.exit(main())
