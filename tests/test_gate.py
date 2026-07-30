"""Tests for the PostToolUse quality gate.

The gate's own subprocess is injected, so nothing here shells out to prek.
"""

import functools
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from gate import GateResult, build_command, check, main, run_subprocess

PASS = GateResult(code=0, output="all hooks passed")
FAIL = GateResult(code=1, output="ruff check....Failed\n  unsorted-imports")


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
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "x.py"))
    )
    assert main([], runner=functools.partial(_runner, PASS)) == 0
    assert not capsys.readouterr().err


def test_failing_gate_blocks_with_exit_2_and_reports_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 is what makes a PostToolUse hook blocking; stderr is what Claude reads."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.stdin.read", functools.partial(_stdin_returning, _payload(tmp_path / "x.py"))
    )
    assert main([], runner=functools.partial(_runner, FAIL)) == 2
    captured = capsys.readouterr()
    assert "unsorted-imports" in captured.err
    assert not captured.out


def test_file_outside_the_repository_is_not_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    monkeypatch.chdir(root)
    outside = _payload(tmp_path / "elsewhere" / "note.md")
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, outside))
    assert main([], runner=functools.partial(_runner, FAIL)) == 0


def test_missing_file_path_is_not_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.read", functools.partial(_stdin_returning, "{}"))
    assert main([], runner=functools.partial(_runner, FAIL)) == 0


# --- the real runner ---------------------------------------------------------------------


def test_missing_executable_fails_open(tmp_path: Path) -> None:
    """A machine without prek must not have every edit blocked."""
    result = run_subprocess(["definitely-not-a-real-binary-xyz"], tmp_path)
    assert result.code == 0
    assert "cannot run" in result.output
