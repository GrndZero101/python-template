"""Report the branch and tree at session start, and anything that has silently switched a guard off.

Claude Code `SessionStart` hook. What it prints becomes context for the agent. With nothing wrong
it prints `git status --short --branch` and nothing else, as the hook always has.

Every guard in this project fails *open* when its tooling is missing — deliberately, because a
broken hook must not block every edit. The price is that a missing tool is invisible: the gate
stops running and nothing says so. This hook is where that becomes visible. It checks:

- **`prek` on PATH.** Without it the edit-time gate, the stop gate and every git hook do nothing.
- **All three git shims** — `pre-commit`, `commit-msg` and `pre-merge-commit`. `prek install`
  alone wires only the first, which silently drops the commit-message check and makes
  `git merge --no-ff` into `main` fail.

When something is wrong it replies in JSON instead, so the agent gets the status plus the problem
and its fix, and the user sees the problem as a warning. It never blocks: a session must always be
able to start, including to fix exactly this.
"""

import argparse
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from gate import Runner, run_subprocess
from hook_payload import find_repo_root, notice

SHIMS = ("pre-commit", "commit-msg", "pre-merge-commit")
STATUS_COMMAND = ["git", "status", "--short", "--branch"]
# Resolves a linked worktree's hooks to the main repository's, and honours `core.hooksPath`.
HOOKS_PATH_COMMAND = ["git", "rev-parse", "--git-path", "hooks"]
INSTALL_SHIMS = "prek install -t pre-commit -t commit-msg -t pre-merge-commit"

Which = Callable[[str], str | None]


def hooks_dir(root: Path, runner: Runner) -> Path | None:
    """Return the directory git runs hooks from, or None if git cannot say."""
    result = runner(HOOKS_PATH_COMMAND, root)
    if not result.ran or result.code != 0 or not result.output:
        return None
    return root / result.output.strip()


def missing_shims(directory: Path) -> list[str]:
    """Return the shims absent from `directory`, in the order they are installed."""
    return [name for name in SHIMS if not (directory / name).is_file()]


def find_problems(root: Path, runner: Runner, which: Which) -> list[str]:
    """Return one line per switched-off guard, each naming its fix."""
    problems: list[str] = []
    if which("prek") is None:
        problems.append(
            "prek is not on PATH, so the edit gate, the stop gate and the git hooks are all off. "
            "Fix: uv tool install prek"
        )
    directory = hooks_dir(root, runner)
    absent = missing_shims(directory) if directory is not None else []
    if absent:
        problems.append(
            f"git hook shim(s) missing: {', '.join(absent)}. Commits skip those checks. "
            f"Fix: {INSTALL_SHIMS}"
        )
    return problems


def render(status: str, problems: list[str]) -> str:
    """Return what the hook prints: the plain status, or a JSON notice when a guard is off."""
    if not problems:
        return status
    listing = "\n".join(f"- {problem}" for problem in problems)
    context = (
        f"{status}\n\nA guard is switched off:\n{listing}\n\n"
        "Tell the user before starting work; they may need to run the fix."
    )
    return notice("SessionStart", context, user_message=f"Guards switched off:\n{listing}")


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    return argparse.ArgumentParser(
        prog="session_doctor",
        description="Report git status, and any guard whose tooling is missing.",
    )


def main(
    argv: list[str] | None = None,
    runner: Runner = run_subprocess,
    which: Which = shutil.which,
) -> int:
    """Entry point. Always returns 0: a session must be able to start, if only to fix this."""
    _build_parser().parse_args(argv)
    root = find_repo_root()
    if root is None:
        return 0
    status = runner(STATUS_COMMAND, root).output
    sys.stdout.write(f"{render(status, find_problems(root, runner, which))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
