"""Tests for the gate's run log."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from gate_log import LOG_NAME, Entry, failed_hooks, record

FIXED_TIME = datetime(2026, 10, 2, 9, 15, tzinfo=UTC)


def _fixed_now() -> datetime:
    return FIXED_TIME


def test_failed_hooks_are_read_from_prek_output_in_order() -> None:
    output = "ruff check....Failed\n- hook id: ruff-check\n  x\nty....Failed\n- hook id: ty\n"
    assert failed_hooks(output) == ("ruff-check", "ty")


def test_record_appends_one_json_line_per_run(tmp_path: Path) -> None:
    record(tmp_path, Entry("gate", "block", "src/x.py", ("ty",)), now=_fixed_now)
    record(tmp_path, Entry("stop-gate", "pass", "3 files"), now=_fixed_now)
    lines = (tmp_path / LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {
        "at": "2026-10-02T09:15:00+00:00",
        "hook": "gate",
        "outcome": "block",
        "target": "src/x.py",
        "failed": ["ty"],
    }
    assert json.loads(lines[1])["failed"] == []


def test_an_unwritable_log_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A log is a measurement; it must never be the reason an edit is blocked."""
    record(tmp_path / "missing-directory", Entry("gate", "pass", "x.py"), now=_fixed_now)
    assert "gate log not written" in capsys.readouterr().err
