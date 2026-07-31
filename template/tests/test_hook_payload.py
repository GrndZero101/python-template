"""Tests for shared hook payload parsing.

Deterministic: every test builds its own tree under `tmp_path`.
"""

import json
from pathlib import Path

import pytest
from hook_payload import find_gate_root, find_repo_root, inside_repo, target_path


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


# --- locating the config that governs an edited file --------------------------------------


def _make_project(directory: Path) -> Path:
    """Create `directory` with a prek config in it and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    return directory


def test_gate_root_is_the_repo_root_in_a_generated_project(tmp_path: Path) -> None:
    """The shape every generated project has: config at the root, source below it."""
    _make_project(tmp_path)
    target = tmp_path / "src" / "pkg" / "x.py"
    target.parent.mkdir(parents=True)
    assert find_gate_root(target, tmp_path) == tmp_path.resolve()


def test_gate_root_prefers_the_nearest_config(tmp_path: Path) -> None:
    """This repo's shape: the template's own config must win over the one at the root."""
    _make_project(tmp_path)
    project = _make_project(tmp_path / "template")
    target = project / "src" / "pkg" / "x.py"
    target.parent.mkdir(parents=True)
    assert find_gate_root(target, tmp_path) == project.resolve()


def test_gate_root_is_none_when_no_config_governs_the_file(tmp_path: Path) -> None:
    """A directory belonging to no project is a legitimate place to edit, so the gate stands down."""
    assert find_gate_root(tmp_path / "TODO.md", tmp_path) is None


def test_gate_root_never_escapes_the_repository(tmp_path: Path) -> None:
    """A config in an ancestor of the repo is somebody else's; the search stops at the root."""
    _make_project(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    assert find_gate_root(root / "x.py", root) is None
