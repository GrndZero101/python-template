"""Tests for the geo coordinate lookup.

No network: every request is served by an httpx MockTransport, so these are
deterministic and run offline.
"""

import functools
import json

import httpx
import pytest

from claude.geo import NOMINATIM_URL, Place, find_coordinates, format_places, main

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


def test_returns_a_place_parsed_from_the_body() -> None:
    with client_returning([CLEVE]) as client:
        places = find_coordinates("cleve", client=client)
    assert places == [
        Place("Cleve, Eyre Peninsula, South Australia, 5640, Australia", -33.7075, 136.4931, "town")
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


def test_format_places_as_text() -> None:
    place = Place("Cleve, South Australia", -33.7075, 136.4931, "town")
    assert format_places([place]) == "-33.707500, 136.493100  (town)  Cleve, South Australia"


def test_format_places_as_json() -> None:
    place = Place("Cleve, South Australia", -33.7075, 136.4931, "town")
    decoded = json.loads(format_places([place], as_json=True))
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
    place = Place("Cleve, South Australia", -33.7075, 136.4931, "town")
    monkeypatch.setattr("claude.geo.find_coordinates", functools.partial(_always, [place]))
    assert main(["get-coordinates", "cleve"]) == 0
    captured = capsys.readouterr()
    assert "Cleve, South Australia" in captured.out


def _record_query(seen_queries: list[str], query: str, **_: object) -> list[Place]:
    """Stand in for find_coordinates, recording the query it was called with."""
    seen_queries.append(query)
    return [Place("x", 0.0, 0.0, "town")]


def test_main_joins_multi_word_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_queries: list[str] = []
    monkeypatch.setattr(
        "claude.geo.find_coordinates", functools.partial(_record_query, seen_queries)
    )
    main(["get-coordinates", "cleve,", "south", "australia"])
    assert seen_queries == ["cleve, south australia"]


def test_main_reports_no_matches_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("claude.geo.find_coordinates", functools.partial(_always, []))
    assert main(["get-coordinates", "nowhere-at-all-xyz"]) == 1
    assert not capsys.readouterr().out
    assert "no matches" in caplog.text


def test_main_reports_unreachable_service_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("claude.geo.find_coordinates", _unreachable)
    assert main(["get-coordinates", "cleve"]) == 1
    assert not capsys.readouterr().out
    assert "could not reach" in caplog.text
    assert "ConnectError" in caplog.text


def test_main_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_nominatim_url_is_the_official_endpoint() -> None:
    assert NOMINATIM_URL == "https://nominatim.openstreetmap.org/search"
