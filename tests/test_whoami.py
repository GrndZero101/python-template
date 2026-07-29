"""Tests for the whoami command.

Deterministic: the user and hostname lookups are injected, so nothing here
depends on the machine the tests run on.
"""

import functools
import json

import pytest

from claude.whoami import Identity, current_identity, format_identity, main


def _fixed(value: str) -> str:
    """Stand in for a lookup that always answers `value`."""
    return value


def _failing() -> str:
    """Stand in for a lookup on a host with no resolvable identity."""
    msg = "no such user"
    raise OSError(msg)


SAMPLE = Identity(user="ada", host="analytical-engine")


def test_current_identity_uses_injected_lookups() -> None:
    identity = current_identity(
        get_user=functools.partial(_fixed, "ada"),
        get_host=functools.partial(_fixed, "analytical-engine"),
    )
    assert identity == SAMPLE


def test_default_format_is_user_at_host() -> None:
    assert format_identity(SAMPLE) == "ada@analytical-engine"


def test_json_format_is_a_single_object() -> None:
    assert json.loads(format_identity(SAMPLE, as_json=True)) == {
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
    assert not captured.err


def test_main_json_flag_emits_parseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("claude.whoami.current_identity", functools.partial(_return, SAMPLE))
    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "user": "ada",
        "host": "analytical-engine",
    }


def test_main_reports_failure_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed lookup exits 1, logs, and leaves stdout empty for consumers."""
    monkeypatch.setattr("claude.whoami.current_identity", _failing)
    assert main([]) == 1
    assert not capsys.readouterr().out
    assert "could not determine" in caplog.text
    assert "OSError" in caplog.text


def test_unknown_flag_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--nope"])
    assert exit_info.value.code == 2


def _return(identity: Identity) -> Identity:
    """Stand in for current_identity with a fixed answer."""
    return identity
