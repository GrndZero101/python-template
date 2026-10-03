"""Tests for finish_branch, against real git repositories under `tmp_path`.

git is the thing being driven, so these run it for real. Only prek is stood in for, because a
throwaway repository has no hooks or gate config. That is also the case the script must survive: a
repository whose commits ran no hook, so its own check is the only one.
"""

import dataclasses
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from finish_branch import main
from gate import GateResult, run_subprocess
from stop_gate import TEST_COMMAND

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

PASS = GateResult(code=0, output="")
FAIL = GateResult(code=1, output="ruff check....Failed")


def _git(root: Path, *args: str) -> str:
    result = run_subprocess(["git", *args], root)
    assert result.code == 0, result.output
    return result.output


@dataclasses.dataclass
class _Prek:
    """Runs git for real and stands in for prek and pytest, recording what it is asked to check."""

    gate: GateResult = PASS
    message_check: GateResult = PASS
    tests: GateResult = PASS
    gate_runs: int = 0
    test_runs: int = 0
    messages: list[str] = dataclasses.field(default_factory=list)

    def __call__(self, command: Sequence[str], cwd: Path) -> GateResult:
        """Answer one command the way the runner would."""
        if list(command) == TEST_COMMAND:
            self.test_runs += 1
            return self.tests
        if command[0] != "prek":
            return run_subprocess(command, cwd)
        if "commit-msg" not in command:
            self.gate_runs += 1
            return self.gate
        message = Path(command[-1]).read_text(encoding="utf-8").strip()
        self.messages.append(message)
        return self.message_check


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
    prek = _Prek()
    assert main(["feat(x): add a and b"], runner=prek) == 0
    assert prek.gate_runs == 1
    assert prek.messages == ["feat(x): add a and b"]
    assert _first_parent_subjects(root) == ["feat(x): add a and b", "chore: start"]
    merged = _git(root, "log", "--format=%s", "main^2")
    assert merged.splitlines()[0] == "feat(x): add a and b", "the branch side is one commit"
    assert _branches(root) == {"main"}


def test_a_one_commit_branch_reuses_its_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    assert main([], runner=_Prek()) == 0
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
    err = capsys.readouterr().err
    assert "not clean: commit it on feat/x" in err
    assert "?? stray.txt" in err


def test_a_commit_a_hook_aborted_is_named_as_such(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The currency run: the hook reformatted staged files, and `-q` hid that nothing committed."""
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "a.py")
    (root / "a.py").write_text("x = 1  # reformatted\n", encoding="utf-8")
    assert main([]) == 1
    assert "a commit hook reformatted staged files" in capsys.readouterr().err


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
    assert main(["--no-merge", "feat(x): add a and b"], runner=_Prek()) == 0
    assert _first_parent_subjects(root) == ["chore: start"]
    assert _branches(root) == {"main", "feat/x", "feat/x-squashed"}


def test_keep_commits_folds_fixups_and_merges_with_a_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    _commit(root, "a2.py", "fixup! feat(x): add a")
    _commit(root, "b.py", "feat(x): add b")
    prek = _Prek()
    assert main(["--keep-commits", "feat(x): add a and b"], runner=prek) == 0
    assert prek.gate_runs == 1
    assert prek.messages == ["feat(x): add a", "feat(x): add b", "feat(x): add a and b"]
    arrived = _git(root, "log", "--format=%s", "main^1..main^2").splitlines()
    assert arrived == ["feat(x): add b", "feat(x): add a"]
    body = _git(root, "log", "-1", "--format=%b", "main")
    assert "feat(x): add b" in body, "--log lists the commits that arrived"


def test_keep_commits_stops_when_the_full_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    assert main(["--keep-commits", "feat(x): add a"], runner=_Prek(gate=FAIL)) == 1
    assert "full gate failed" in capsys.readouterr().err
    assert _first_parent_subjects(root) == ["chore: start"]


def test_a_one_commit_branch_is_gated_before_it_is_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    assert main([], runner=_Prek(gate=FAIL)) == 1
    assert "full gate failed" in capsys.readouterr().err
    assert _first_parent_subjects(root) == ["chore: start"]
    assert _git(root, "branch", "--show-current") == "feat/x"


def test_a_squash_the_gate_refuses_returns_to_the_untouched_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "chore(x): wip")
    _commit(root, "b.py", "chore(x): wip again")
    before = _git(root, "rev-parse", "HEAD")
    assert main(["feat(x): add a and b"], runner=_Prek(gate=FAIL)) == 1
    assert _first_parent_subjects(root) == ["chore: start"]
    assert _git(root, "branch", "--show-current") == "feat/x"
    assert _git(root, "rev-parse", "HEAD") == before
    assert _branches(root) == {"main", "feat/x"}


def test_a_commit_message_that_fails_the_check_is_not_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "added a")
    assert main([], runner=_Prek(message_check=FAIL)) == 1
    assert "rejected 'added a'" in capsys.readouterr().err
    assert _first_parent_subjects(root) == ["chore: start"]


def test_failing_tests_are_not_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate does not run the tests, and nothing else will once the branch is merged."""
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    failing = GateResult(code=1, output="FAILED tests/test_a.py::test_a")
    assert main([], runner=_Prek(tests=failing)) == 1
    err = capsys.readouterr().err
    assert "the tests failed" in err
    assert "FAILED tests/test_a.py::test_a" in err
    assert _first_parent_subjects(root) == ["chore: start"]
    assert _git(root, "branch", "--show-current") == "feat/x"


def test_no_tests_skips_the_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path, monkeypatch)
    _commit(root, "a.py", "feat(x): add a")
    prek = _Prek(tests=GateResult(code=1, output="never run"))
    assert main(["--no-tests"], runner=prek) == 0
    assert prek.test_runs == 0
    assert _first_parent_subjects(root) == ["feat(x): add a", "chore: start"]
