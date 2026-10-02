"""Tests for the Stop hook that refuses, once, to end a turn on a red work tree.

Every subprocess is injected: a runner answers git, prek and pytest from a table, so nothing here
shells out except the one test that exercises real git.
"""

import functools
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from gate import GateResult, Scanner, run_subprocess
from gate_log import LOG_NAME
from stop_gate import (
    NO_TESTS_COLLECTED,
    SECTION_LIMIT,
    TEST_COMMAND,
    changed_files,
    clip_head,
    clip_tail,
    main,
)

PASS = GateResult(code=0, output="")
GATE_FAIL = GateResult(
    code=1, output="ruff check....Failed\n- hook id: ruff-check\n  src/x.py:1:1: F401 unused"
)
TESTS_FAIL = GateResult(code=1, output="F\nFAILED tests/test_x.py::test_x - assert 1 == 2")
PREK_MISSING = GateResult(code=0, output="cannot run prek", ran=False)

Table = dict[str, GateResult]
Calls = list[Sequence[str]]


def _dispatch(table: Table, calls: Calls, command: Sequence[str], cwd: Path) -> GateResult:
    """Runner that records each command and answers by its first two words."""
    del cwd
    calls.append(command)
    key = " ".join(command[:2])
    return table.get(key, PASS)


def _changes(*names: str) -> GateResult:
    """What `git diff --name-only -z` prints for `names`."""
    return GateResult(code=0, output="\0".join(names))


def _no_conflicts(root: Path) -> list[str]:
    del root
    return []


def _conflicted(root: Path) -> list[str]:
    del root
    return ["README.md"]


def _stdin_returning(payload: str) -> str:
    return payload


def _project(root: Path, monkeypatch: pytest.MonkeyPatch, *files: str) -> Path:
    """Make `root` a repository with a gate config and `files`, and run from it."""
    (root / ".git").mkdir()
    (root / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def _stopping(monkeypatch: pytest.MonkeyPatch, *, active: bool = False) -> None:
    payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": active})
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, payload))


def _run_main(
    table: Table,
    calls: Calls,
    argv: list[str] | None = None,
    scanner: Scanner = _no_conflicts,
) -> int:
    return main(argv or [], runner=functools.partial(_dispatch, table, calls), scanner=scanner)


def _log(root: Path) -> list[dict[str, object]]:
    lines = (root / LOG_NAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# --- when it stays out of the way ---------------------------------------------------------


def test_a_second_stop_is_always_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocking only once is what keeps an agent that cannot finish from looping."""
    _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch, active=True)
    calls: Calls = []
    assert _run_main({"git diff": _changes("src/x.py"), "prek run": GATE_FAIL}, calls) == 0
    assert calls == []


def test_a_turn_that_changed_nothing_checks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, monkeypatch)
    _stopping(monkeypatch)
    calls: Calls = []
    assert _run_main({"prek run": GATE_FAIL}, calls) == 0
    assert all(command[0] == "git" for command in calls)


def test_conflict_markers_pause_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path, monkeypatch, "README.md")
    _stopping(monkeypatch)
    calls: Calls = []
    table = {"git diff": _changes("README.md"), "prek run": GATE_FAIL}
    assert _run_main(table, calls, scanner=_conflicted) == 0
    assert not [command for command in calls if command[0] == "prek"]
    assert _log(root)[0]["outcome"] == "paused"


def test_missing_prek_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch)
    table = {"git diff": _changes("src/x.py"), "prek run": PREK_MISSING}
    assert _run_main(table, [], ["--no-tests"]) == 0
    assert _log(root)[0]["outcome"] == "skipped"


def test_no_tests_collected_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch)
    empty_suite = GateResult(code=NO_TESTS_COLLECTED, output="no tests ran")
    assert _run_main({"git diff": _changes("src/x.py"), "uv run": empty_suite}, []) == 0


# --- when it blocks -----------------------------------------------------------------------


def test_a_gate_failure_blocks_and_names_the_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch)
    assert _run_main({"git diff": _changes("src/x.py"), "prek run": GATE_FAIL}, []) == 2
    err = capsys.readouterr().err
    assert "[gate]" in err
    assert "F401 unused" in err
    assert "[tests" not in err
    entry = _log(root)[0]
    assert (entry["outcome"], entry["failed"]) == ("block", ["ruff-check"])


def test_a_test_failure_blocks_and_shows_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch)
    assert _run_main({"git diff": _changes("src/x.py"), "uv run": TESTS_FAIL}, []) == 2
    assert "FAILED tests/test_x.py::test_x" in capsys.readouterr().err
    assert _log(root)[0]["failed"] == ["pytest"]


def test_untracked_files_are_gated_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file written with a heredoc is exactly what PostToolUse never saw."""
    _project(tmp_path, monkeypatch, "src/new.py")
    _stopping(monkeypatch)
    calls: Calls = []
    _run_main({"git ls-files": _changes("src/new.py")}, calls, ["--no-tests"])
    prek = next(command for command in calls if command[0] == "prek")
    assert str(Path("src/new.py")) in prek


def test_no_tests_flag_skips_the_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, monkeypatch, "src/x.py")
    _stopping(monkeypatch)
    calls: Calls = []
    assert _run_main({"git diff": _changes("src/x.py")}, calls, ["--no-tests"]) == 0
    assert TEST_COMMAND not in [list(command) for command in calls]


# --- pieces -------------------------------------------------------------------------------


def test_head_and_tail_mark_what_they_cut() -> None:
    text = "a" * SECTION_LIMIT + "END"
    assert clip_head(text).endswith("[... 3 more characters cut]")
    assert clip_tail(text).startswith("[... 3 characters cut]")
    assert clip_tail(text).endswith("END")
    assert clip_head("short") == "short"


def _git(tmp_path: Path, *args: str) -> None:
    result = run_subprocess(["git", *args], tmp_path)
    assert result.code == 0, result.output


def test_changed_files_finds_modified_and_untracked_but_not_deleted(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    for name in ("kept.py", "edited.py", "deleted.py"):
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "--quiet", "-m", "init")
    (tmp_path / "edited.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "deleted.py").unlink()
    (tmp_path / "new file.py").write_text("x = 3\n", encoding="utf-8")
    found = changed_files(tmp_path, run_subprocess)
    assert sorted(found) == [Path("edited.py"), Path("new file.py")]
