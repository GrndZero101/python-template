"""Tests for the public-IP lookup.

No network: every request is served by an httpx MockTransport, so these are
deterministic and run offline.
"""

import functools

import httpx
import pytest

from claude.publicip import CHECKIP_URL, fetch_public_ip, main, parse_ip


def _make_response(status: int, body: str, _request: httpx.Request) -> httpx.Response:
    """MockTransport handler: build a fresh response for every request."""
    return httpx.Response(status, text=body)


def client_returning(body: str = "203.0.113.7\n", status: int = 200) -> httpx.Client:
    """Return a client whose every request answers with `body` and `status`."""
    handler = functools.partial(_make_response, status, body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _unreachable(**_: object) -> str:
    """Stand in for fetch_public_ip when the service cannot be reached."""
    msg = "connection refused"
    raise httpx.ConnectError(msg)


def _always(address: str, **_: object) -> str:
    """Stand in for fetch_public_ip with a fixed answer."""
    return address


def test_returns_the_address_from_the_body() -> None:
    with client_returning("203.0.113.7\n") as client:
        assert fetch_public_ip(client=client) == "203.0.113.7"


def test_accepts_ipv6() -> None:
    with client_returning("2001:db8::1\n") as client:
        assert fetch_public_ip(client=client) == "2001:db8::1"


def test_http_error_propagates() -> None:
    with client_returning(status=503) as client, pytest.raises(httpx.HTTPStatusError):
        fetch_public_ip(client=client)


def test_caller_supplied_client_is_not_closed() -> None:
    """The function must not close a client it does not own."""
    with client_returning() as client:
        fetch_public_ip(client=client)
        assert not client.is_closed


@pytest.mark.parametrize("body", ["", "   \n", "not-an-ip", "203.0.113.999"])
def test_rejects_bodies_that_are_not_addresses(body: str) -> None:
    with pytest.raises(ValueError, match=CHECKIP_URL):
        parse_ip(body)


def test_error_names_the_offending_value() -> None:
    with pytest.raises(ValueError, match="banana"):
        parse_ip("banana")


def test_parse_ip_strips_whitespace() -> None:
    assert parse_ip("  198.51.100.4  \n") == "198.51.100.4"


def test_main_prints_address_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "claude.publicip.fetch_public_ip",
        functools.partial(_always, "203.0.113.7"),
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "203.0.113.7\n"


def test_main_reports_unreachable_service_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failures exit 1 and are logged; stdout stays empty so pipelines see nothing."""
    monkeypatch.setattr("claude.publicip.fetch_public_ip", _unreachable)
    assert main([]) == 1
    assert not capsys.readouterr().out
    assert "could not reach" in caplog.text
    # logger.exception keeps the traceback that says where it started
    assert "ConnectError" in caplog.text
