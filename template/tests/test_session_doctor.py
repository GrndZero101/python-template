"""Tests for the SessionStart hook that reports switched-off guards.

git and PATH lookups are injected, so nothing here shells out.
"""

import functools
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from gate import GateResult
from session_doctor import INSTALL_SHIMS, SHIMS, main, missing_shims, render

STATUS = "## feat/x...origin/feat/x"


def _git(hooks: str, command: Sequence[str], cwd: Path) -> GateResult:
    """Answer `git status` with STATUS and `git rev-parse --git-path hooks` with `hooks`."""
    del cwd
    if "rev-parse" in command:
        return GateResult(code=0, output=hooks)
    return GateResult(code=0, output=STATUS)


def _found(name: str) -> str | None:
    return f"/usr/bin/{name}"


def _not_found(name: str) -> str | None:
    del name
    return None


def _repo(root: Path, monkeypatch: pytest.MonkeyPatch, shims: Sequence[str] = SHIMS) -> None:
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True)
    for name in shims:
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.chdir(root)


def test_a_healthy_project_prints_only_the_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    assert main([], runner=runner, which=_found) == 0
    assert capsys.readouterr().out == f"{STATUS}\n"


def test_missing_prek_is_reported_with_its_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch)
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    assert main([], runner=runner, which=_not_found) == 0
    reply = json.loads(capsys.readouterr().out)
    assert "uv tool install prek" in reply["systemMessage"]
    assert STATUS in reply["hookSpecificOutput"]["additionalContext"]


def test_a_missing_shim_is_named_with_the_command_that_installs_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`prek install` alone wires pre-commit only — the commonest way to end up here."""
    _repo(tmp_path, monkeypatch, shims=["pre-commit"])
    runner = functools.partial(_git, str(Path(".git") / "hooks"))
    main([], runner=runner, which=_found)
    message = json.loads(capsys.readouterr().out)["systemMessage"]
    assert "commit-msg, pre-merge-commit" in message
    assert INSTALL_SHIMS in message


def test_missing_shims_keeps_install_order(tmp_path: Path) -> None:
    (tmp_path / "commit-msg").write_text("", encoding="utf-8")
    assert missing_shims(tmp_path) == ["pre-commit", "pre-merge-commit"]


def test_render_is_plain_text_without_problems() -> None:
    assert render("## main", []) == "## main"


def test_outside_a_repository_it_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = functools.partial(_git, ".git/hooks")
    assert main([], runner=runner, which=_not_found) == 0
    assert not capsys.readouterr().out
