"""Tests for the whoami command.

Deterministic: the user and hostname lookups are injected, so nothing here
depends on the machine the tests run on. Log assertions add a local loguru
sink and disable the app's own logging setup, since loguru does not
propagate to pytest's `caplog` and `configure_logging` would otherwise strip
any sink a test installs.
"""

import functools
import json

import pytest
from loguru import logger

from claude.whoami import Identity, OutputFormat, current_identity, main, render_identity


def _fixed(value: str) -> str:
    """Stand in for a lookup that always answers `value`."""
    return value


def _failing() -> str:
    """Stand in for a lookup on a host with no resolvable identity."""
    msg = "no such user"
    raise OSError(msg)


def _return(identity: Identity) -> Identity:
    """Stand in for current_identity with a fixed answer."""
    return identity


def _no_op_configure_logging(*, verbose: bool = False) -> None:
    """Stand in for configure_logging so a test's own sink survives."""


SAMPLE = Identity(user="ada", host="analytical-engine")


def test_current_identity_uses_injected_lookups() -> None:
    identity = current_identity(
        get_user=functools.partial(_fixed, "ada"),
        get_host=functools.partial(_fixed, "analytical-engine"),
    )
    assert identity == SAMPLE


def test_default_format_is_user_at_host() -> None:
    assert render_identity(SAMPLE, OutputFormat.text) == "ada@analytical-engine"


def test_json_format_is_a_single_object() -> None:
    assert json.loads(render_identity(SAMPLE, OutputFormat.json)) == {
        "user": "ada",
        "host": "analytical-engine",
    }


def test_main_prints_user_at_host_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("claude.whoami.current_identity", functools.partial(_return, SAMPLE))
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ada@analytical-engine\n"


def test_main_output_json_emits_parseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("claude.whoami.current_identity", functools.partial(_return, SAMPLE))
    assert main(["--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "user": "ada",
        "host": "analytical-engine",
    }


def test_main_reports_failure_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed lookup exits 1, logs, and leaves stdout empty for consumers."""
    monkeypatch.setattr("claude.whoami.current_identity", _failing)
    monkeypatch.setattr("claude.whoami.configure_logging", _no_op_configure_logging)
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), format="{message}")
    try:
        assert main([]) == 1
    finally:
        logger.remove(sink_id)
    assert not capsys.readouterr().out
    assert any("could not determine" in message for message in messages)


def test_unknown_flag_is_a_usage_error() -> None:
    assert main(["--nope"]) == 2
