"""Refuse edits to files inside the repository while on a protected branch.

Reads a Claude Code `PreToolUse` hook payload on stdin. Exit 0 allows the tool call;
exit 2 blocks it and feeds stderr back to the agent as the error to resolve.

Only files *inside* the repository are guarded. Writes to a scratchpad, to memory, or
anywhere else outside the work tree are none of this hook's business — blocking those was
the defect this module replaces.

Two deliberate implementation choices:

- **`pathlib`, not string comparison.** Path containment is case-insensitive and
  separator-agnostic on Windows and case-sensitive on POSIX. `pathlib` gets both right with
  no branching, which a portable shell one-liner could not.
- **No `subprocess`.** This runs before every single edit, so two `git` spawns per keystroke
  is real latency. Reading `.git` directly is faster and keeps the module free of security
  lint suppressions.
"""

import argparse
import dataclasses
import sys
from pathlib import Path

from hook_payload import find_repo_root, inside_repo, target_path

SENTINEL = ".allow-main-edit"
HEAD_PREFIX = "ref: refs/heads/"
GITDIR_PREFIX = "gitdir: "
BLOCK = 2


@dataclasses.dataclass(frozen=True)
class Decision:
    """Whether to block a tool call, and why."""

    blocked: bool
    reason: str


def git_dir(root: Path) -> Path:
    """Return the `.git` directory, following a linked-worktree pointer file."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    try:
        pointer = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return dot_git
    if pointer.startswith(GITDIR_PREFIX):
        return Path(pointer.removeprefix(GITDIR_PREFIX))
    return dot_git


def read_branch(root: Path) -> str | None:
    """Return the checked-out branch name, or None when detached or unreadable."""
    try:
        head = (git_dir(root) / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith(HEAD_PREFIX):
        return None
    return head.removeprefix(HEAD_PREFIX)


def branch_reason(branch: str | None, protected: frozenset[str]) -> str | None:
    """Return why the branch itself permits the edit, or None when it is protected."""
    if branch is None:
        return "detached HEAD, no branch to protect"
    if branch not in protected:
        return f"on unprotected branch {branch}"
    return None


def decide(
    target: Path | None,
    root: Path | None,
    branch: str | None,
    protected: frozenset[str],
) -> Decision:
    """Return the decision for one tool call. Pure: every input is an argument."""
    if target is None:
        return Decision(blocked=False, reason="no file path in payload")
    if root is None:
        return Decision(blocked=False, reason="not inside a git repository")
    allowed = branch_reason(branch, protected)
    if allowed is not None:
        return Decision(blocked=False, reason=allowed)
    if not inside_repo(target, root):
        return Decision(blocked=False, reason="file is outside the repository")
    if (root / SENTINEL).exists():
        return Decision(blocked=False, reason=f"{SENTINEL} override present")
    return Decision(blocked=True, reason=f"on protected branch {branch}")


def refusal(branch: str) -> str:
    """Return the message shown to the agent when an edit is refused."""
    return (
        f"Refusing to edit repository files while on '{branch}'. Branch first:\n"
        f"  git switch -c <type>/<short-name>\n"
        f"Types match the commit list in CLAUDE.md: "
        f"feat, fix, docs, refactor, test, chore, build, ci, perf, style, revert.\n"
        f"To override deliberately: touch {SENTINEL}"
    )


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="branch_guard",
        description="Block edits to repository files while on a protected branch.",
    )
    parser.add_argument(
        "--protected",
        nargs="+",
        default=["main"],
        metavar="BRANCH",
        help="branch names to protect (default: main)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    root = find_repo_root()
    branch = read_branch(root) if root else None
    decision = decide(
        target=target_path(sys.stdin.read()),
        root=root,
        branch=branch,
        protected=frozenset(args.protected),
    )
    if not decision.blocked:
        return 0
    sys.stderr.write(refusal(branch or "?") + "\n")
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())
