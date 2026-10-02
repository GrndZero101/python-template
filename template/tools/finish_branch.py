"""Finish a branch: consolidate it, gate it, and merge it into `main` the way this project requires.

The `git-workflow` skill describes the rules; this script carries them out, so the steps are run
rather than remembered. Run it from the branch being finished:

    uv run python tools/finish_branch.py "feat(geo): add coordinate lookup"
    uv run python tools/finish_branch.py --keep-commits "feat(geo): add lookup and caching"
    uv run python tools/finish_branch.py --no-merge "fix(cli): exit 2 on a bad flag"

**Default — squash.** The branch's commits are squashed onto a new branch cut from the current
`main`, committed there with MESSAGE (the full gate and the commit-message check run on that
commit), and merged into `main` with `--no-ff` and the same subject. Both branches are then
deleted. A branch that is already one commit on top of `main` is merged as it is, and MESSAGE may
be omitted to reuse its subject.

**`--keep-commits` — rebase in place**, for a branch that genuinely holds more than one change.
`fixup!` commits are folded in with an autosquash rebase, `prek run --all-files` runs (no hook runs
during a rebase, so this is the only check the rebased tree gets), and the branch is merged with
`--no-ff --log`, so the body lists the commits that arrived.

**`--no-merge`** stops before touching `main`, leaving the consolidated branch for review.

Nothing is lost on failure. The original branch is never rewritten on the default path, and on
any failure the script returns to it and says what to do next. Exit 0 when merged (or ready, with
`--no-merge`), 1 when a step failed, 2 on a usage error.
"""

import argparse
import dataclasses
import sys
from pathlib import Path

from gate import GateResult, Runner, run_subprocess
from hook_payload import find_repo_root

USAGE = 2
FAILED = 1
SQUASH_SUFFIX = "-squashed"


class FinishError(Exception):
    """A step failed. The message says what happened and what to do next."""


@dataclasses.dataclass(frozen=True)
class Plan:
    """What the script will do, settled before anything changes."""

    root: Path
    branch: str
    base: str
    message: str
    commits: int
    on_base_tip: bool


def _git(runner: Runner, root: Path, *args: str) -> GateResult:
    """Run one git command in `root`."""
    return runner(["git", *args], root)


def _require(result: GateResult, what: str) -> str:
    """Return `result`'s output, or raise naming `what` failed and why."""
    if result.ran and result.code == 0:
        return result.output
    msg = f"{what} failed:\n{result.output}"
    raise FinishError(msg)


def plan(root: Path, base: str, message: str | None, runner: Runner) -> Plan:
    """Check the starting state and settle the merge message, changing nothing."""
    branch = _require(_git(runner, root, "branch", "--show-current"), "reading the branch")
    if not branch or branch == base:
        msg = f"run this from the branch being finished, not {branch or 'a detached HEAD'}"
        raise FinishError(msg)
    if _require(_git(runner, root, "status", "--porcelain"), "reading the tree"):
        msg = "the tree is not clean; commit or stash everything first"
        raise FinishError(msg)
    count = _require(_git(runner, root, "rev-list", "--count", f"{base}..HEAD"), "counting")
    commits = int(count)
    if commits == 0:
        msg = f"{branch} has no commits that are not already on {base}; nothing to finish"
        raise FinishError(msg)
    fork = _require(_git(runner, root, "merge-base", base, "HEAD"), "finding the fork point")
    tip = _require(_git(runner, root, "rev-parse", base), f"reading {base}")
    if message is None:
        if commits != 1:
            msg = f'{branch} has {commits} commits; pass the merge message, e.g. "feat(x): ..."'
            raise FinishError(msg)
        message = _require(_git(runner, root, "log", "-1", "--format=%s"), "reading the subject")
    return Plan(root, branch, base, message, commits, on_base_tip=fork == tip)


def _restore(target: Plan, runner: Runner, scratch: str) -> None:
    """Abandon `scratch` and return to the original branch, which was never changed."""
    _git(runner, target.root, "reset", "--hard", "--quiet")
    _git(runner, target.root, "switch", "--quiet", target.branch)
    _git(runner, target.root, "branch", "-D", scratch)


def squash(target: Plan, runner: Runner) -> str:
    """Return the branch to merge, holding the whole change as one commit made through the gate.

    A branch that is already one commit on the base tip is returned as it is.
    """
    if target.commits == 1 and target.on_base_tip:
        return target.branch
    scratch = f"{target.branch}{SQUASH_SUFFIX}"
    _require(
        _git(runner, target.root, "switch", "--quiet", "-c", scratch, target.base), "branching"
    )
    merged = _git(runner, target.root, "merge", "--squash", target.branch)
    if merged.code != 0:
        _restore(target, runner, scratch)
        msg = (
            f"{target.base} has moved and conflicts with {target.branch}. On {target.branch}, run "
            f"`git rebase {target.base}`, resolve the conflicts there, then run this again.\n"
            f"{merged.output}"
        )
        raise FinishError(msg)
    committed = _git(runner, target.root, "commit", "--quiet", "-m", target.message)
    if committed.code != 0:
        _restore(target, runner, scratch)
        msg = (
            f"the gate refused the squashed commit, so nothing was merged. Fix it on "
            f"{target.branch} and run this again.\n{committed.output}"
        )
        raise FinishError(msg)
    return scratch


def rebase_in_place(target: Plan, runner: Runner) -> str:
    """Fold `fixup!` commits in, then run the full gate the rebase skipped."""
    # `-i` with a no-op sequence editor applies the autosquash order without stopping to ask.
    autosquash = ("-c", "sequence.editor=true", "rebase", "-i", "--autosquash", target.base)
    rebased = _git(runner, target.root, *autosquash)
    if rebased.code != 0:
        _git(runner, target.root, "rebase", "--abort")
        msg = f"the autosquash rebase stopped; it has been aborted.\n{rebased.output}"
        raise FinishError(msg)
    gate = runner(["prek", "run", "--all-files"], target.root)
    if not gate.ran or gate.code != 0:
        msg = f"the full gate failed after the rebase; fix it on {target.branch}.\n{gate.output}"
        raise FinishError(msg)
    return target.branch


def merge(target: Plan, source: str, runner: Runner, *, log: bool) -> str:
    """Merge `source` into the base with `--no-ff`, delete the finished branches, return the sha."""
    _require(
        _git(runner, target.root, "switch", "--quiet", target.base), f"switching to {target.base}"
    )
    command = [
        "merge",
        "--no-ff",
        "--quiet",
        "-m",
        target.message,
        *(["--log"] if log else []),
        source,
    ]
    merged = _git(runner, target.root, *command)
    if merged.code != 0:
        _git(runner, target.root, "merge", "--abort")
        _git(runner, target.root, "switch", "--quiet", source)
        msg = (
            f"the merge into {target.base} was refused; you are back on {source}.\n{merged.output}"
        )
        raise FinishError(msg)
    for name in dict.fromkeys([source, target.branch]):
        _git(runner, target.root, "branch", "-D", name)
    return _require(_git(runner, target.root, "rev-parse", "--short", "HEAD"), "reading the merge")


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="finish_branch",
        description="Consolidate the current branch, gate it, and merge it into main.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="the merge subject, a Conventional Commit summary; optional for a one-commit branch",
    )
    parser.add_argument(
        "--keep-commits",
        action="store_true",
        help="rebase in place, folding fixups, instead of squashing to one commit",
    )
    parser.add_argument(
        "--no-merge", action="store_true", help="stop before main, leaving the branch for review"
    )
    parser.add_argument("--base", default="main", help="the branch to merge into (default: main)")
    return parser


def finish(args: argparse.Namespace, root: Path, runner: Runner) -> str:
    """Carry out the whole procedure and return what to tell the user."""
    if args.keep_commits and args.message is None:
        msg = "--keep-commits needs a merge message that summarises the whole branch"
        raise FinishError(msg)
    target = plan(root, args.base, args.message, runner)
    source = rebase_in_place(target, runner) if args.keep_commits else squash(target, runner)
    if args.no_merge:
        return f"{source} is ready to merge into {target.base} as {target.message!r}"
    sha = merge(target, source, runner, log=args.keep_commits)
    return f"merged into {target.base} as {sha}: {target.message}"


def main(argv: list[str] | None = None, runner: Runner = run_subprocess) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    root = find_repo_root()
    if root is None:
        sys.stderr.write("finish_branch: not inside a git repository\n")
        return USAGE
    try:
        summary = finish(args, root, runner)
    except FinishError as exc:
        sys.stderr.write(f"finish_branch: {exc}\n")
        return FAILED
    sys.stdout.write(f"{summary}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
