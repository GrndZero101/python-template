"""Tests for finish_branch, against real git repositories under `tmp_path`.

git is the thing being driven, so these run it for real. Only prek is stood in for, because a
throwaway repository has no hooks or gate config; the script's own commits therefore run unhooked.
"""

import functools
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from finish_branch import main
from gate import GateResult, run_subprocess

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

PASS = GateResult(code=0, output="")
FAIL = GateResult(code=1, output="ruff check....Failed")


def _git(root: Path, *args: str) -> str:
    result = run_subprocess(["git", *args], root)
    assert result.code == 0, result.output
    return result.output


def _routing(prek: GateResult, command: Sequence[str], cwd: Path) -> GateResult:
    """Run git for real; answer prek with `prek`."""
    if command[0] == "prek":
        return prek
    return run_subprocess(command, cwd)


def _commit(root: Path, name: str, message: str) -> None:
    (root / name).write_text(f"{message}\n", encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "--quiet", "-m", message)


def _repo(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository on `main` with one commit, then on `feat/x`; the test runs from it."""
    _git(root, "init", "--quiet", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _commit(root, "README.md", "chore: start")
    _git(root, "switch", "--quiet", "-c", "feat/x")
    monkeypatch.chdir(root)
    return root


def _first_parent_subjects(root: Path) -> list[str]:
    return _git(root, "log", "--first-parent", "--format=%s", "main").splitlines()


def _branches(root: Path) -> set[str]:
    return set(_git(root, "branch", "--format=%(refname:short)").splitlines())


def test_squashes_several_commits_into_one_merged_with_no_ff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "chore(x): wip")
    _commit(root, "b.py", "chore(x): wip again")
    assert main(["feat(x): add a and b"]) == 0
    assert _first_parent_subjects(root) == ["feat(x): add a and b", "chore: start"]
    merged = _git(root, "log", "--format=%s", "main^2")
    assert merged.splitlines()[0] == "feat(x): add a and b", "the branch side is one commit"
    assert _branches(root) == {"main"}


def test_a_one_commit_branch_reuses_its_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    assert main([]) == 0
    assert _first_parent_subjects(root)[0] == "feat(x): add a"
    assert _git(root, "rev-list", "--count", "main^1..main^2") == "1"


def test_several_commits_without_a_message_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "chore(x): wip")
    _commit(root, "b.py", "chore(x): wip again")
    assert main([]) == 1
    assert "pass the merge message" in capsys.readouterr().err
    assert _git(root, "branch", "--show-current") == "feat/x"


def test_a_dirty_tree_is_refused_before_anything_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    (root / "stray.txt").write_text("x\n", encoding="utf-8")
    assert main([]) == 1
    assert "not clean" in capsys.readouterr().err


def test_running_on_main_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _git(root, "switch", "--quiet", "main")
    assert main(["feat(x): nothing"]) == 1
    assert "not main" in capsys.readouterr().err


def test_a_conflict_with_main_leaves_the_branch_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "README.md", "docs: branch side")
    _commit(root, "a.py", "chore(x): wip")
    _git(root, "switch", "--quiet", "main")
    _commit(root, "README.md", "docs: main side")
    _git(root, "switch", "--quiet", "feat/x")
    before = _git(root, "rev-parse", "HEAD")
    assert main(["feat(x): conflicting"]) == 1
    assert "git rebase main" in capsys.readouterr().err
    assert _git(root, "branch", "--show-current") == "feat/x"
    assert _git(root, "rev-parse", "HEAD") == before
    assert _branches(root) == {"main", "feat/x"}


def test_no_merge_stops_with_the_squashed_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "chore(x): wip")
    _commit(root, "b.py", "chore(x): wip again")
    assert main(["--no-merge", "feat(x): add a and b"]) == 0
    assert _first_parent_subjects(root) == ["chore: start"]
    assert _branches(root) == {"main", "feat/x", "feat/x-squashed"}


def test_keep_commits_folds_fixups_and_merges_with_a_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    _commit(root, "a2.py", "fixup! feat(x): add a")
    _commit(root, "b.py", "feat(x): add b")
    runner = functools.partial(_routing, PASS)
    assert main(["--keep-commits", "feat(x): add a and b"], runner=runner) == 0
    arrived = _git(root, "log", "--format=%s", "main^1..main^2").splitlines()
    assert arrived == ["feat(x): add b", "feat(x): add a"]
    body = _git(root, "log", "-1", "--format=%b", "main")
    assert "feat(x): add b" in body, "--log lists the commits that arrived"


def test_keep_commits_stops_when_the_full_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    runner = functools.partial(_routing, FAIL)
    assert main(["--keep-commits", "feat(x): add a"], runner=runner) == 1
    assert "full gate failed" in capsys.readouterr().err
    assert _first_parent_subjects(root) == ["chore: start"]
