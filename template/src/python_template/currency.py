"""Convert currency and show the cost of an FX margin, using the Frankfurter API.

Frankfurter needs no key and imposes no User-Agent restriction, but note that
`api.frankfurter.app` issues a 301 to `api.frankfurter.dev/v1/`. httpx does not follow
redirects by default, unlike requests, so the `.dev` host is used directly here.

Every monetary value is a `Decimal`. Rates are parsed straight out of the response text with
`parse_float=Decimal`, so a rate never passes through a float and never picks up a binary
rounding artifact on the way in. Margin arithmetic on floats is the one way a tool like this
can be wrong invisibly.
"""

import datetime as dt
import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Annotated

import httpx
import typer
from loguru import logger
from pydantic import BaseModel
from rich.table import Table

from python_template.logging_setup import configure_logging
from python_template.output import OutputFormat, OutputOption, out

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
DEFAULT_TIMEOUT_SECONDS = 10.0
MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
PERCENT = Decimal(100)
PAIR_PARTS = 2


class ConversionRequest(BaseModel):
    """What the caller asked for, once parsed and validated."""

    amount: Decimal
    base: str
    quote: str
    margin_percent: Decimal


class RateQuote(BaseModel):
    """A single interbank rate, as published."""

    base: str
    quote: str
    rate: Decimal
    on: dt.date


class Conversion(BaseModel):
    """The result of converting an amount, with and without an FX margin applied."""

    quote: RateQuote
    amount: Decimal
    margin_percent: Decimal
    effective_rate: Decimal
    interbank_amount: Decimal
    effective_amount: Decimal
    margin_cost: Decimal


def parse_pair(raw: str) -> tuple[str, str]:
    """Split an FX pair like `GBP/AUD` into its base and quote codes."""
    parts = raw.upper().split("/")
    if len(parts) != PAIR_PARTS or not all(parts):
        msg = f"expected a currency pair like GBP/AUD, got {raw!r}"
        raise ValueError(msg)
    return parts[0], parts[1]


def parse_decimal(raw: str, label: str) -> Decimal:
    """Parse `raw` as an exact Decimal.

    Typer cannot bind a `Decimal` parameter, so amounts arrive as strings. That is the better
    boundary anyway: `Decimal("0.1")` is exactly one tenth, whereas any numeric CLI type would
    round-trip through a float first and arrive already wrong.
    """
    try:
        return Decimal(raw)
    except InvalidOperation:
        msg = f"expected a number for {label}, got {raw!r}"
        raise ValueError(msg) from None


def parse_request(amount: str, pair: str, margin: str) -> ConversionRequest:
    """Turn raw command-line strings into a validated request."""
    base, quote = parse_pair(pair)
    return ConversionRequest(
        amount=parse_decimal(amount, "amount"),
        base=base,
        quote=quote,
        margin_percent=parse_decimal(margin, "margin"),
    )


def _request_rate(client: httpx.Client, base: str, quote: str, timeout: float) -> RateQuote:
    """Fetch one interbank rate using an already-open client."""
    response = client.get(
        FRANKFURTER_URL,
        params={"base": base, "symbols": quote},
        timeout=timeout,
    )
    response.raise_for_status()
    # parse_float=Decimal keeps the rate out of binary floating point entirely.
    payload = json.loads(response.text, parse_float=Decimal)
    rates = payload["rates"]
    if quote not in rates:
        msg = f"{quote} is not quoted against {base}; try `cli currency --help` for the format"
        raise ValueError(msg)
    return RateQuote(
        base=payload["base"],
        quote=quote,
        rate=Decimal(rates[quote]),
        on=dt.date.fromisoformat(payload["date"]),
    )


def fetch_rate(
    base: str,
    quote: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> RateQuote:
    """Return the current interbank rate for `base`/`quote`.

    Pass `client` to reuse a connection or substitute a transport in tests; when omitted, a
    client is opened and closed around the single request.
    """
    if client is not None:
        return _request_rate(client, base, quote, timeout)
    with httpx.Client() as owned_client:
        return _request_rate(owned_client, base, quote, timeout)


def convert(quote: RateQuote, amount: Decimal, margin_percent: Decimal) -> Conversion:
    """Apply `margin_percent` to an interbank rate and report what it costs.

    A provider quoting a retail rate shaves its margin off the interbank rate, so the customer
    receives less. Pure: given the same inputs it always returns the same result, which makes it
    callable with literal arguments from a breakpoint.
    """
    effective_rate = (quote.rate * (PERCENT - margin_percent) / PERCENT).quantize(RATE)
    interbank_amount = (amount * quote.rate).quantize(MONEY)
    effective_amount = (amount * effective_rate).quantize(MONEY)
    return Conversion(
        quote=quote,
        amount=amount,
        margin_percent=margin_percent,
        effective_rate=effective_rate,
        interbank_amount=interbank_amount,
        effective_amount=effective_amount,
        margin_cost=interbank_amount - effective_amount,
    )


def render_conversion_json(conversion: Conversion) -> str:
    """Render `conversion` as a JSON object, with Decimals as strings."""
    return conversion.model_dump_json()


def _build_conversion_table(conversion: Conversion) -> Table:
    """Return a rich Table describing one conversion."""
    quote = conversion.quote
    table = Table(title=f"{quote.base}/{quote.quote} on {quote.on.isoformat()}")
    table.add_column("Measure")
    table.add_column("Value", justify="right")
    table.add_row("Amount", f"{conversion.amount:,.2f} {quote.base}")
    table.add_row("Interbank rate", f"{quote.rate}")
    table.add_row("Margin", f"{conversion.margin_percent}%")
    table.add_row("Effective rate", f"{conversion.effective_rate}")
    table.add_row("At interbank", f"{conversion.interbank_amount:,.2f} {quote.quote}")
    table.add_row("You receive", f"{conversion.effective_amount:,.2f} {quote.quote}")
    table.add_row("Cost of margin", f"{conversion.margin_cost:,.2f} {quote.quote}")
    return table


def emit(conversion: Conversion, fmt: OutputFormat) -> None:
    """Write `conversion` to stdout in the requested format."""
    if fmt is OutputFormat.json:
        sys.stdout.write(render_conversion_json(conversion) + "\n")
        return
    out.print(_build_conversion_table(conversion))


def currency(
    amount: Annotated[str, typer.Argument(help="amount to convert, e.g. 1000")],
    pair: Annotated[str, typer.Argument(help="currency pair, e.g. GBP/AUD")],
    margin: Annotated[
        str, typer.Option("--margin", "-m", help="FX margin percent applied to the rate")
    ] = "0",
    output: OutputOption = OutputFormat.table,
    *,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="log request details to stderr")
    ] = False,
) -> None:
    """Convert an amount between currencies and show what an FX margin costs."""
    configure_logging(verbose=verbose)
    try:
        request = parse_request(amount, pair, margin)
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(2) from None

    logger.debug("fetching {}/{} from Frankfurter", request.base, request.quote)
    try:
        quote = fetch_rate(request.base, request.quote)
    except httpx.HTTPError:
        logger.exception("could not reach {}", FRANKFURTER_URL)
        raise typer.Exit(1) from None
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(1) from None

    emit(convert(quote, request.amount, request.margin_percent), output)
