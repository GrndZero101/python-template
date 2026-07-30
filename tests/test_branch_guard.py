"""Tests for the PreToolUse branch guard.

Deterministic: every test builds its own fake work tree under `tmp_path`, so nothing
depends on the branch this suite happens to run on.
"""

import functools
import json
from pathlib import Path

import pytest
from branch_guard import (
    SENTINEL,
    Decision,
    decide,
    find_repo_root,
    git_dir,
    main,
    read_branch,
    target_path,
)

MAIN = frozenset({"main"})
BOTH = frozenset({"main", "master"})


def _stdin_returning(payload: str) -> str:
    """Stand in for sys.stdin.read with a fixed payload."""
    return payload


def _work_tree(root: Path, branch: str | None = "main") -> Path:
    """Create a minimal .git directory with HEAD pointing at `branch`."""
    dot_git = root / ".git"
    dot_git.mkdir(parents=True, exist_ok=True)
    head = f"ref: refs/heads/{branch}\n" if branch else "9f8e7d6c5b4a\n"
    (dot_git / "HEAD").write_text(head, encoding="utf-8")
    return root


# --- decide(): the pure decision table ------------------------------------------------


def test_blocks_repo_file_on_protected_branch(tmp_path: Path) -> None:
    root = _work_tree(tmp_path)
    verdict = decide(root / "src" / "x.py", root, "main", MAIN)
    assert verdict == Decision(blocked=True, reason="on protected branch main")


def test_allows_repo_file_on_feature_branch(tmp_path: Path) -> None:
    root = _work_tree(tmp_path, "feat/x")
    assert decide(root / "src" / "x.py", root, "feat/x", MAIN).blocked is False


def test_allows_file_outside_the_repository(tmp_path: Path) -> None:
    """The defect this module was written to fix: memory and scratchpad writes."""
    root = _work_tree(tmp_path / "repo")
    outside = tmp_path / "memory" / "note.md"
    verdict = decide(outside, root, "main", MAIN)
    assert verdict.blocked is False
    assert "outside the repository" in verdict.reason


def test_sentinel_overrides_the_block(tmp_path: Path) -> None:
    root = _work_tree(tmp_path)
    (root / SENTINEL).write_text("", encoding="utf-8")
    verdict = decide(root / "x.py", root, "main", MAIN)
    assert verdict.blocked is False
    assert SENTINEL in verdict.reason


def test_allows_when_detached_head(tmp_path: Path) -> None:
    root = _work_tree(tmp_path, branch=None)
    assert decide(root / "x.py", root, None, MAIN).blocked is False


def test_allows_when_not_a_repository(tmp_path: Path) -> None:
    assert decide(tmp_path / "x.py", None, "main", MAIN).blocked is False


def test_allows_when_payload_has_no_path(tmp_path: Path) -> None:
    root = _work_tree(tmp_path)
    assert decide(None, root, "main", MAIN).blocked is False


def test_protects_every_configured_branch(tmp_path: Path) -> None:
    root = _work_tree(tmp_path, "master")
    assert decide(root / "x.py", root, "master", BOTH).blocked is True
    assert decide(root / "x.py", root, "master", MAIN).blocked is False


# --- payload parsing -------------------------------------------------------------------


def test_extracts_file_path_from_payload() -> None:
    payload = json.dumps({"tool_input": {"file_path": "/repo/src/x.py"}})
    assert target_path(payload) == Path("/repo/src/x.py")


def test_backslash_path_survives_json_round_trip() -> None:
    r"""A Windows payload carries C:\repo\x.py; json handles the escaping, not us."""
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
def test_malformed_payloads_fail_open(payload: str) -> None:
    """None means allow. A parse error must never block every edit in a session."""
    assert target_path(payload) is None


# --- reading git state without subprocess ---------------------------------------------


def test_finds_repo_root_from_a_nested_directory(tmp_path: Path) -> None:
    root = _work_tree(tmp_path)
    nested = root / "src" / "deep" / "deeper"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == root.resolve()


def test_returns_none_outside_any_repository(tmp_path: Path) -> None:
    assert find_repo_root(tmp_path) is None


def test_reads_branch_from_head(tmp_path: Path) -> None:
    root = _work_tree(tmp_path, "feat/some-thing")
    assert read_branch(root) == "feat/some-thing"


def test_detached_head_reads_as_no_branch(tmp_path: Path) -> None:
    root = _work_tree(tmp_path, branch=None)
    assert read_branch(root) is None


def test_git_dir_follows_a_worktree_pointer(tmp_path: Path) -> None:
    """A linked worktree has .git as a file, not a directory."""
    real = tmp_path / "main-repo" / ".git" / "worktrees" / "wt"
    real.mkdir(parents=True)
    (real / "HEAD").write_text("ref: refs/heads/feat/wt\n", encoding="utf-8")
    tree = tmp_path / "wt"
    tree.mkdir()
    (tree / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")
    assert git_dir(tree) == real
    assert read_branch(tree) == "feat/wt"


# --- entry point -----------------------------------------------------------------------


def test_main_blocks_with_exit_2_and_writes_to_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 is what makes a PreToolUse hook blocking; stderr is what Claude reads."""
    root = _work_tree(tmp_path)
    monkeypatch.chdir(root)
    payload = json.dumps({"tool_input": {"file_path": str(root / "x.py")}})
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, payload))
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "git switch -c" in captured.err
    assert not captured.out


def test_main_allows_outside_file_with_exit_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _work_tree(tmp_path / "repo")
    monkeypatch.chdir(root)
    payload = json.dumps({"tool_input": {"file_path": str(tmp_path / "outside.md")}})
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, payload))
    assert main([]) == 0
    assert not capsys.readouterr().err
