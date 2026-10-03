"""Refuse, once, to end a turn while the changed files fail the gate or the tests fail.

Claude Code `Stop` hook. The `PostToolUse` gate sees only the `Edit`, `Write` and `NotebookEdit`
tools, so a file changed any other way — `sed`, a heredoc, a script the agent ran, a formatter —
reaches the end of the turn unchecked. This closes that path: when the agent tries to stop, every
file the branch has changed goes through the same prek gate, and the test suite runs. Anything red
blocks the stop with exit 2, and stderr tells the agent what to fix.

"Changed" is measured from where the branch left `main` (`--base`), not from `HEAD`. An agent that
commits before it stops would otherwise leave a clean tree and nothing to check: the commit hook
lints, but it never runs the tests. On `main` itself, or with no `main` to compare against, it is
the files that differ from `HEAD`, plus the untracked ones either way.

It blocks **at most once per stop**. Claude Code sets `stop_hook_active` on the payload when the
agent is already continuing because of a stop hook, and this hook then lets it stop whatever the
state. An agent that genuinely cannot finish can still end its turn and say so, and the session
never meets Claude Code's cap on consecutive stop-hook continuations.

It stays out of the way otherwise:

- **No changes, no checks.** On `main` with a clean tree, a turn that only answered a question
  costs nothing. On a branch with commits it costs one gate run and the tests, every stop, until
  the branch is merged: the price of a commit never escaping the check.
- **Conflict markers pause it**, as they pause the edit-time gate: the agent may be stopping
  precisely to ask how a conflict should be resolved.
- **prek missing fails open**, as the edit-time gate does; that gate has already said so.

`--no-tests` skips the suite. The template repository uses it, because its suite generates five
projects and takes a minute; its `generation-tests` hook is skipped for the same reason.

Every run that checked something appends one line to `.gate.log` (see `gate_log.py`).
"""

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from gate import (
    SKIP_HOOKS,
    GateResult,
    Runner,
    Scanner,
    check,
    condense,
    find_conflicted,
    run_concise,
)
from gate_log import Entry, Outcome, failed_hooks, record
from hook_payload import find_repo_root, has_gate_config, parse_payload

BLOCK = 2
TEST_COMMAND = ["uv", "run", "python", "-m", "pytest", "-q", "-x", "--tb=short", "--no-header"]
# pytest's exit code when it collected no tests at all; a project with no tests yet is not red.
NO_TESTS_COLLECTED = 5
# Each section of the report is clipped so the whole stays well under Claude Code's 10,000
# character cap on hook output; past that it is replaced by a file path the agent never reads.
SECTION_LIMIT = 4000
BASE_BRANCH = "main"
MERGE_BASE = ["git", "merge-base", "HEAD"]
TRACKED_CHANGES = ["git", "diff", "--name-only", "-z"]
UNTRACKED_FILES = ["git", "ls-files", "--others", "--exclude-standard", "-z"]


@dataclasses.dataclass(frozen=True)
class StopReport:
    """What the gate and the test suite said about the changed files."""

    gate: GateResult
    tests: GateResult | None


def _names(result: GateResult) -> list[str]:
    """Split NUL-separated git output into names, or nothing if git failed or did not run."""
    if not result.ran or result.code != 0:
        return []
    return [name for name in result.output.split("\0") if name]


def diff_base(root: Path, runner: Runner, base: str = BASE_BRANCH) -> str:
    """Return the commit where the current branch left `base`, or `HEAD` when there is none.

    On `base` itself the merge-base is `HEAD`, so the diff is the uncommitted work, as it should be.
    """
    result = runner([*MERGE_BASE, base], root)
    fork = result.output.strip() if result.ran and result.code == 0 else ""
    return fork or "HEAD"


def changed_files(root: Path, runner: Runner, base: str = BASE_BRANCH) -> list[Path]:
    """Return the files the branch has changed since it left `base`, untracked ones included.

    Committed and uncommitted changes alike, so a commit made during the turn is still checked.
    `-z` keeps unusual file names intact. A deleted file still appears in the diff, but there is
    nothing left on disk to check, so only paths that are files now are returned.
    """
    tracked = runner([*TRACKED_CHANGES, diff_base(root, runner, base)], root)
    names = [*_names(tracked), *_names(runner(UNTRACKED_FILES, root))]
    unique = dict.fromkeys(names)
    return [Path(name) for name in unique if (root / name).is_file()]


def run_tests(root: Path, runner: Runner) -> GateResult:
    """Run the project's test suite, counting "no tests collected" as a pass."""
    result = runner(TEST_COMMAND, root)
    if result.code == NO_TESTS_COLLECTED:
        return dataclasses.replace(result, code=0)
    return result


def evaluate(
    paths: Sequence[Path], root: Path, *, skip: str, tests: bool, runner: Runner
) -> StopReport:
    """Gate `paths` and, unless told not to, run the tests. Both run so one reply covers both."""
    gate = check(paths, root, skip, runner)
    suite = run_tests(root, runner) if tests else None
    return StopReport(gate=gate, tests=suite)


def outcome_of(report: StopReport) -> Outcome:
    """Classify a stop report for the log."""
    if not report.gate.ran:
        return "skipped"
    if report.gate.code != 0 or (report.tests is not None and report.tests.code != 0):
        return "block"
    return "fixed" if report.gate.rerun else "pass"


def _failed(report: StopReport) -> tuple[str, ...]:
    """Return the failing hook ids, plus `pytest` when the suite failed."""
    hooks = failed_hooks(report.gate.output) if report.gate.code != 0 else ()
    if report.tests is not None and report.tests.code != 0:
        return (*hooks, "pytest")
    return hooks


def clip_head(text: str, limit: int = SECTION_LIMIT) -> str:
    """Return the start of `text`, marked if anything was cut. prek reports the worst first."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n[... {len(text) - limit} more characters cut]"


def clip_tail(text: str, limit: int = SECTION_LIMIT) -> str:
    """Return the end of `text`, marked if anything was cut. pytest summarises at the end."""
    if len(text) <= limit:
        return text
    return f"[... {len(text) - limit} characters cut]\n{text[-limit:]}"


def block_message(report: StopReport) -> str:
    """Return what the agent is told when the stop is refused."""
    sections = ["Not finished: the changed files do not pass. Fix this, then stop."]
    if report.gate.ran and report.gate.code != 0:
        sections.append(f"[gate]\n{clip_head(condense(report.gate.output))}")
    if report.tests is not None and report.tests.code != 0:
        sections.append(f"[tests: {' '.join(TEST_COMMAND)}]\n{clip_tail(report.tests.output)}")
    sections.append(
        "If it cannot be fixed now, stopping again is allowed: say what is still failing and why."
    )
    return "\n\n".join(sections)


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="stop_gate",
        description="Refuse once to end a turn while changed files fail the gate or tests fail.",
    )
    parser.add_argument(
        "--skip",
        default=SKIP_HOOKS,
        metavar="HOOKS",
        help=f"comma-separated hook ids to skip (default: {SKIP_HOOKS})",
    )
    parser.add_argument("--no-tests", action="store_true", help="do not run the test suite")
    parser.add_argument(
        "--base",
        default=BASE_BRANCH,
        help=f"the branch changes are measured from (default: {BASE_BRANCH})",
    )
    return parser


def main(
    argv: list[str] | None = None,
    runner: Runner = run_concise,
    scanner: Scanner = find_conflicted,
) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    if parse_payload(sys.stdin.read()).get("stop_hook_active") is True:
        return 0
    root = find_repo_root()
    if root is None or not has_gate_config(root):
        return 0
    paths = changed_files(root, runner, args.base)
    if not paths:
        return 0
    target = f"{len(paths)} changed file(s)"
    if scanner(root):
        record(root, Entry(hook="stop-gate", outcome="paused", target=target))
        return 0
    report = evaluate(paths, root, skip=args.skip, tests=not args.no_tests, runner=runner)
    outcome = outcome_of(report)
    record(root, Entry(hook="stop-gate", outcome=outcome, target=target, failed=_failed(report)))
    if outcome != "block":
        return 0
    sys.stderr.write(f"{block_message(report)}\n")
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())
