"""Tests for shared hook payload parsing.

Deterministic: every test builds its own tree under `tmp_path`.
"""

import json
from pathlib import Path

import pytest
from hook_payload import find_repo_root, inside_repo, target_path


def test_extracts_file_path_from_payload() -> None:
    payload = json.dumps({"tool_input": {"file_path": "/repo/src/x.py"}})
    assert target_path(payload) == Path("/repo/src/x.py")


def test_backslash_path_survives_json_round_trip() -> None:
    r"""A Windows payload carries C:\repo\x.py; json owns the escaping, not us."""
    payload = json.dumps({"tool_input": {"file_path": r"C:\repo\x.py"}})
    assert target_path(payload) == Path(r"C:\repo\x.py")


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "[]",
        "{}",
        '{"tool_input": null}',
        '{"tool_input": {}}',
        '{"tool_input": {"file_path": ""}}',
        '{"tool_input": {"file_path": 42}}',
    ],
)
def test_malformed_payloads_fail_soft(payload: str) -> None:
    """None means "no opinion". A parse error must never block a whole session."""
    assert target_path(payload) is None


def test_finds_repo_root_from_a_nested_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "src" / "deep" / "deeper"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == tmp_path.resolve()


def test_returns_none_outside_any_repository(tmp_path: Path) -> None:
    assert find_repo_root(tmp_path) is None


def test_inside_repo_accepts_a_nested_file(tmp_path: Path) -> None:
    assert inside_repo(tmp_path / "src" / "x.py", tmp_path) is True


def test_inside_repo_rejects_a_sibling_directory(tmp_path: Path) -> None:
    """The defect these hooks were rewritten to fix: memory and scratchpad writes."""
    root = tmp_path / "repo"
    root.mkdir()
    assert inside_repo(tmp_path / "elsewhere" / "note.md", root) is False
