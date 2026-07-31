"""Tests for the geo coordinate lookup.

No network: every request is served by an httpx MockTransport, so these are
deterministic and run offline. Log assertions add a local loguru sink and
disable the app's own logging setup, since loguru does not propagate to
pytest's `caplog` and `configure_logging` would otherwise strip any sink a
test installs.
"""

import functools
import json

import httpx
import pytest
from loguru import logger

from python_template.cli import main
from python_template.geo import NOMINATIM_URL, Place, find_coordinates, render_places_json

CLEVE = {
    "display_name": "Cleve, Eyre Peninsula, South Australia, 5640, Australia",
    "lat": "-33.7075",
    "lon": "136.4931",
    "type": "town",
}
CLEVELAND = {
    "display_name": "Cleveland, Ohio, United States",
    "lat": "41.4995",
    "lon": "-81.6954",
    "type": "city",
}


def _make_response(status: int, body: str, _request: httpx.Request) -> httpx.Response:
    """MockTransport handler: build a fresh response for every request."""
    return httpx.Response(status, text=body)


def client_returning(
    results: list[dict[str, str]] | None = None, status: int = 200
) -> httpx.Client:
    """Return a client whose every request answers with `results` and `status`."""
    body = json.dumps(results if results is not None else [CLEVE])
    handler = functools.partial(_make_response, status, body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _unreachable(*_args: object, **_kwargs: object) -> list[Place]:
    """Stand in for find_coordinates when the service cannot be reached."""
    msg = "connection refused"
    raise httpx.ConnectError(msg)


def _always(places: list[Place], *_args: object, **_kwargs: object) -> list[Place]:
    """Stand in for find_coordinates with a fixed answer."""
    return places


def _record_query(seen_queries: list[str], query: str, **_kwargs: object) -> list[Place]:
    """Stand in for find_coordinates, recording the query it was called with."""
    seen_queries.append(query)
    return [Place(display_name="x", lat=0.0, lon=0.0, type="town")]


def _no_op_configure_logging(*, verbose: bool = False) -> None:
    """Stand in for configure_logging so a test's own sink survives."""


def test_returns_a_place_parsed_from_the_body() -> None:
    with client_returning([CLEVE]) as client:
        places = find_coordinates("cleve", client=client)
    assert places == [
        Place(
            display_name="Cleve, Eyre Peninsula, South Australia, 5640, Australia",
            lat=-33.7075,
            lon=136.4931,
            type="town",
        )
    ]


def test_returns_every_match() -> None:
    with client_returning([CLEVE, CLEVELAND]) as client:
        places = find_coordinates("cleve", client=client)
    assert len(places) == 2


def test_returns_empty_list_when_nothing_matches() -> None:
    with client_returning([]) as client:
        assert find_coordinates("nowhere-at-all-xyz", client=client) == []


def test_http_error_propagates() -> None:
    with client_returning(status=503) as client, pytest.raises(httpx.HTTPStatusError):
        find_coordinates("cleve", client=client)


def test_caller_supplied_client_is_not_closed() -> None:
    """The function must not close a client it does not own."""
    with client_returning() as client:
        find_coordinates("cleve", client=client)
        assert not client.is_closed


def test_render_places_json() -> None:
    place = Place(display_name="Cleve, South Australia", lat=-33.7075, lon=136.4931, type="town")
    decoded = json.loads(render_places_json([place]))
    assert decoded == [
        {
            "display_name": "Cleve, South Australia",
            "latitude": -33.7075,
            "longitude": 136.4931,
            "place_type": "town",
        }
    ]


def test_main_prints_matches_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    place = Place(display_name="Cleve, South Australia", lat=-33.7075, lon=136.4931, type="town")
    monkeypatch.setattr("python_template.geo.find_coordinates", functools.partial(_always, [place]))
    assert main(["geo", "cleve"]) == 0
    captured = capsys.readouterr()
    assert "Cleve, South Australia" in captured.out


def test_main_output_json_emits_parseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    place = Place(display_name="Cleve, South Australia", lat=-33.7075, lon=136.4931, type="town")
    monkeypatch.setattr("python_template.geo.find_coordinates", functools.partial(_always, [place]))
    assert main(["geo", "cleve", "--output", "json"]) == 0
    decoded = json.loads(capsys.readouterr().out)
    assert decoded[0]["display_name"] == "Cleve, South Australia"


def test_main_joins_multi_word_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_queries: list[str] = []
    monkeypatch.setattr(
        "python_template.geo.find_coordinates", functools.partial(_record_query, seen_queries)
    )
    main(["geo", "cleve,", "south", "australia"])
    assert seen_queries == ["cleve, south australia"]


def test_main_reports_no_matches_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("python_template.geo.find_coordinates", functools.partial(_always, []))
    monkeypatch.setattr("python_template.geo.configure_logging", _no_op_configure_logging)
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), format="{message}")
    try:
        assert main(["geo", "nowhere-at-all-xyz"]) == 1
    finally:
        logger.remove(sink_id)
    assert not capsys.readouterr().out
    assert any("no matches" in message for message in messages)


def test_main_reports_unreachable_service_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("python_template.geo.find_coordinates", _unreachable)
    monkeypatch.setattr("python_template.geo.configure_logging", _no_op_configure_logging)
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), format="{message}")
    try:
        assert main(["geo", "cleve"]) == 1
    finally:
        logger.remove(sink_id)
    assert not capsys.readouterr().out
    assert any("could not reach" in message for message in messages)


def test_main_requires_a_subcommand() -> None:
    assert main([]) == 0


def test_unknown_subcommand_is_a_usage_error() -> None:
    assert main(["bogus"]) == 2


def test_nominatim_url_is_the_official_endpoint() -> None:
    assert NOMINATIM_URL == "https://nominatim.openstreetmap.org/search"
