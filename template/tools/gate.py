"""Run the quality gate against the file a tool just edited.

Claude Code `PostToolUse` hook. Exit 0 lets the edit stand; exit 2 blocks it and feeds
stderr back to the agent as the error to fix.

Delegates to `prek run --files <path>` rather than invoking ruff, ty and rumdl directly. That
matters for two reasons:

- **One list, not two.** The checks are declared once in `.pre-commit-config.yaml` and used by
  both this hook and the git hooks, so the edit-time gate and the commit-time gate cannot
  drift apart. The previous shell one-liner duplicated the list inside `settings.json`.
- **Portability.** A single executable invocation with no shell operators runs identically on
  Windows, Linux, macOS and in containers. The chained `&&` version needed a POSIX shell and
  failed *open* where none existed.

`prek run --all-files` is deliberately not used: it only sees tracked files, so a newly
created file — exactly what an agent produces — would go unchecked. Naming the path explicitly
covers untracked files too.

While any file still holds conflict markers — mid-way through a `copier update` or a merge — the
gate pauses and lists those files instead. `ty` checks the whole project, so every edit to one
conflicted file would otherwise reprint the syntax errors from all the others, burying the one
result that mattered.
"""

import argparse
import dataclasses
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from hook_payload import find_gate_root, find_repo_root, owning_repo, target_path

BLOCK = 2
# The branch guard owns branch protection; running it here would fail every edit made on main.
SKIP_HOOKS = "no-commit-to-branch"
# The opening and closing markers git and copier both write, matched as check-merge-conflict
# matches them: at the start of a line, followed by a space and the side's label.
CONFLICT_PATTERN = "^(<<<<<<<|>>>>>>>) "


@dataclasses.dataclass(frozen=True)
class GateResult:
    """Outcome of one gate run."""

    code: int
    output: str


Runner = Callable[[Sequence[str], Path], GateResult]
Scanner = Callable[[Path], list[str]]


def run_subprocess(command: Sequence[str], cwd: Path) -> GateResult:
    """Execute `command` in `cwd` and capture its combined output.

    The default runner. Injected as a parameter everywhere else so tests never shell out.
    """
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return GateResult(code=0, output=f"gate skipped: cannot run {command[0]}: {exc}")
    merged = f"{completed.stdout}{completed.stderr}".strip()
    return GateResult(code=completed.returncode, output=merged)


def build_command(path: Path, skip: str = SKIP_HOOKS) -> list[str]:
    """Return the prek invocation that checks exactly `path`.

    `skip` is comma-separated, but prek's `--skip` flag takes exactly one hook id and is
    repeated for more — only the `SKIP` environment variable splits on commas. Passed whole,
    `a,b` names a hook that does not exist, and prek skips nothing.
    """
    command = ["prek", "run", "--files", str(path)]
    for hook_id in skip.split(","):
        stripped = hook_id.strip()
        if stripped:
            command.extend(["--skip", stripped])
    return command


def find_conflicted(root: Path, runner: Runner = run_subprocess) -> list[str]:
    """Return the files under `root`, tracked or untracked, that still hold conflict markers.

    `git grep` prints paths relative to `root`. Anything in its output that does not name a file
    there is a diagnostic — git missing, `root` not a work tree — and the scan fails open on it.
    """
    command = ["git", "grep", "--untracked", "-I", "-l", "-E", CONFLICT_PATTERN]
    result = runner(command, root)
    if result.code != 0:
        return []
    lines = result.output.splitlines()
    return [line for line in lines if (root / line).is_file()]


def paused_message(conflicted: Sequence[str]) -> str:
    """Return what the agent is told while conflict markers remain."""
    listing = "\n".join(f"  {name}" for name in conflicted)
    return (
        f"gate paused: {len(conflicted)} file(s) still hold conflict markers, so every check "
        f"would report only their syntax errors. The full gate resumes once these are "
        f"resolved:\n{listing}"
    )


def check(target: Path, root: Path, skip: str, runner: Runner) -> GateResult:
    """Run the gate for one edited file."""
    return runner(build_command(target, skip), root)


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="gate",
        description="Run the prek gate against the file a tool just edited.",
    )
    parser.add_argument(
        "--skip",
        default=SKIP_HOOKS,
        metavar="HOOKS",
        help=f"comma-separated hook ids to skip (default: {SKIP_HOOKS})",
    )
    return parser


def main(
    argv: list[str] | None = None,
    runner: Runner = run_subprocess,
    scanner: Scanner = find_conflicted,
) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    target = target_path(sys.stdin.read())
    session_root = find_repo_root()
    if target is None or session_root is None:
        return 0
    root = owning_repo(target, session_root)
    gate_root = find_gate_root(target, root) if root else None
    if gate_root is None:
        return 0
    conflicted = scanner(gate_root)
    if conflicted:
        sys.stderr.write(f"{paused_message(conflicted)}\n")
        return BLOCK
    result = check(target, gate_root, args.skip, runner)
    if result.code == 0:
        return 0
    sys.stderr.write(f"{result.output}\n")
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())
