"""Tests for the pytest shim the DebugMCP CLI launches as its `program`.

The runner is injected, so nothing here starts a nested pytest session.
"""

import functools

import pytest
from debug_pytest import main


def _recording_run(calls: list[list[str]], exit_code: int, args: list[str]) -> int:
    """Stand in for pytest.main: record the arguments and return a fixed exit code."""
    calls.append(args)
    return exit_code


def test_passes_arguments_through_unchanged() -> None:
    calls: list[list[str]] = []
    main(["tests/test_x.py", "-q"], run=functools.partial(_recording_run, calls, 0))
    assert calls == [["tests/test_x.py", "-q"]]


def test_returns_the_runner_exit_code() -> None:
    failed = pytest.ExitCode.TESTS_FAILED
    assert main([], run=functools.partial(_recording_run, [], failed)) == failed


def test_defaults_to_the_process_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("sys.argv", ["debug_pytest.py", "tests/test_y.py", "-x"])
    main(run=functools.partial(_recording_run, calls, 0))
    assert calls == [["tests/test_y.py", "-x"]]
