"""Tests for the PostToolUse quality gate.

The gate's own subprocess is injected, so nothing here shells out to prek.
"""

import functools
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from gate import (
    GateResult,
    build_command,
    check,
    find_conflicted,
    main,
    paused_message,
    run_subprocess,
)

PASS = GateResult(code=0, output="all hooks passed")
FAIL = GateResult(code=1, output="ruff check....Failed\n  unsorted-imports")
# Built rather than written out, so this file never trips check-merge-conflict itself.
OPENING_MARKER = "<" * 7 + " before updating"


def _no_conflicts(root: Path) -> list[str]:
    """Stand in for the conflict scan, finding nothing."""
    del root
    return []


def _conflicts(names: list[str], root: Path) -> list[str]:
    """Stand in for the conflict scan, finding `names`."""
    del root
    return names


def _runner(result: GateResult, command: Sequence[str], cwd: Path) -> GateResult:
    """Stand in for the subprocess runner, recording nothing and returning `result`."""
    del command, cwd
    return result


def _stdin_returning(payload: str) -> str:
    """Stand in for sys.stdin.read with a fixed payload."""
    return payload


def _recording(
    seen: list[tuple[Sequence[str], Path]],
    command: Sequence[str],
    cwd: Path,
) -> GateResult:
    """Runner that records what it was asked to run, then reports success."""
    seen.append((command, cwd))
    return PASS


def _payload(path: Path) -> str:
    return json.dumps({"tool_input": {"file_path": str(path)}})


def _make_repo(root: Path) -> Path:
    """Create a repository root the gate will act on: a `.git` entry and a prek config."""
    (root / ".git").mkdir(parents=True)
    (root / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    return root


# --- command construction ---------------------------------------------------------------


def test_command_names_the_edited_file_explicitly() -> None:
    """--files, not --all-files: prek skips untracked files, which agents create constantly."""
    target = Path("src/x.py")
    command = build_command(target, skip="no-commit-to-branch")
    assert command[:3] == ["prek", "run", "--files"]
    assert "--all-files" not in command
    # str(Path(...)), not a literal: the separator differs by platform.
    assert command[3] == str(target)


def test_command_skips_the_branch_hook() -> None:
    """Branch protection is the PreToolUse guard's job; running it here fails every edit on main."""
    command = build_command(Path("src/x.py"))
    assert "--skip" in command
    assert "no-commit-to-branch" in command


def test_each_skipped_hook_gets_its_own_flag() -> None:
    """prek's --skip takes one id; `a,b` passed whole matches no hook and skips nothing."""
    command = build_command(Path("src/x.py"), skip="no-commit-to-branch, generation-tests")
    skips = command[command.index("--skip") :]
    assert skips == ["--skip", "no-commit-to-branch", "--skip", "generation-tests"]


def test_an_empty_skip_list_adds_no_flag() -> None:
    assert "--skip" not in build_command(Path("src/x.py"), skip="")


def test_check_forwards_command_and_cwd(tmp_path: Path) -> None:
    seen: list[tuple[Sequence[str], Path]] = []
    check(
        tmp_path / "x.py",
        tmp_path,
        "no-commit-to-branch",
        functools.partial(_recording, seen),
    )
    assert len(seen) == 1
    assert seen[0][1] == tmp_path


# --- entry point ------------------------------------------------------------------------


def test_passing_gate_allows_the_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "x.py"))
    )
    assert main([], runner=functools.partial(_runner, PASS), scanner=_no_conflicts) == 0
    assert not capsys.readouterr().err


def test_failing_gate_blocks_with_exit_2_and_reports_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 is what makes a PostToolUse hook blocking; stderr is what Claude reads."""
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "x.py"))
    )
    assert main([], runner=functools.partial(_runner, FAIL), scanner=_no_conflicts) == 2
    captured = capsys.readouterr()
    assert "unsorted-imports" in captured.err
    assert not captured.out


def test_file_outside_the_repository_is_not_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_repo(tmp_path / "repo")
    monkeypatch.chdir(root)
    outside = _payload(tmp_path / "elsewhere" / "note.md")
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, outside))
    assert main([], runner=functools.partial(_runner, FAIL), scanner=_no_conflicts) == 0


def test_file_governed_by_no_config_is_not_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This repo's own root holds markdown and no project; editing it must not block."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "TODO.md"))
    )
    assert main([], runner=functools.partial(_runner, FAIL), scanner=_no_conflicts) == 0


def test_gate_runs_from_the_directory_holding_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The template lives one level down, so prek must run there, not at the repo root."""
    (tmp_path / ".git").mkdir()
    project = _make_repo(tmp_path / "template")
    monkeypatch.chdir(tmp_path)
    target = project / "src" / "x.py"
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, _payload(target)))
    seen: list[tuple[Sequence[str], Path]] = []
    assert main([], runner=functools.partial(_recording, seen), scanner=_no_conflicts) == 0
    assert seen[0][1] == project.resolve()


def test_missing_file_path_is_not_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, "{}"))
    assert main([], runner=functools.partial(_runner, FAIL), scanner=_no_conflicts) == 0


def test_conflict_markers_pause_the_gate_and_name_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mid-update, prek would only reprint every conflicted file's syntax errors."""
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "x.py"))
    )
    seen: list[tuple[Sequence[str], Path]] = []
    scanner = functools.partial(_conflicts, ["README.md", "src/x.py"])
    assert main([], runner=functools.partial(_recording, seen), scanner=scanner) == 2
    assert not seen
    err = capsys.readouterr().err
    assert "gate paused" in err
    assert "README.md" in err
    assert "src/x.py" in err


def test_paused_message_lists_one_file_per_line() -> None:
    lines = paused_message(["a.md", "b.py"]).splitlines()
    assert lines[-2:] == ["  a.md", "  b.py"]


def test_scan_keeps_only_paths_that_name_files(tmp_path: Path) -> None:
    """A diagnostic in git's output must not be mistaken for a conflicted file."""
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    output = "README.md\ngate skipped: cannot run git"
    found = find_conflicted(tmp_path, functools.partial(_runner, GateResult(0, output)))
    assert found == ["README.md"]


def test_scan_finds_nothing_when_git_reports_no_match(tmp_path: Path) -> None:
    """`git grep` exits 1 for no match, and anything else is an error; both mean no pause."""
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    assert not find_conflicted(tmp_path, functools.partial(_runner, GateResult(1, "README.md")))


# --- the real runner ---------------------------------------------------------------------


def test_missing_executable_fails_open(tmp_path: Path) -> None:
    """A machine without prek must not have every edit blocked."""
    result = run_subprocess(["definitely-not-a-real-binary-xyz"], tmp_path)
    assert result.code == 0
    assert "cannot run" in result.output


def test_scan_finds_markers_in_tracked_and_untracked_files(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    assert run_subprocess(["git", "init", "--quiet"], tmp_path).code == 0
    conflicted = f"{OPENING_MARKER}\nold\n=======\nnew\n" + ">" * 7 + " after updating\n"
    (tmp_path / "notes.md").write_text(conflicted, encoding="utf-8")
    (tmp_path / "clean.md").write_text(f"quoted: {OPENING_MARKER}\n", encoding="utf-8")
    assert find_conflicted(tmp_path) == ["notes.md"]
