"""Shared parsing for Claude Code hook payloads, and the one shape of reply that does not block.

Both `branch_guard` and `gate` are handed the same JSON on stdin and both need the same two
answers from it: which file is being touched, and where the repository root is. That logic
lives here so the two hooks cannot drift apart.

Every function fails soft — a malformed payload yields None rather than raising. A hook that
crashes on unexpected input would block every edit in the session, which is worse than the
check it was performing.
"""

import json
from pathlib import Path

# `Edit` and `Write` send `file_path`; `NotebookEdit` sends `notebook_path`. Reading only the first
# left every notebook unguarded even though the hook's matcher named the tool.
PATH_KEYS = ("file_path", "notebook_path")


def parse_payload(payload: str) -> dict[str, object]:
    """Decode a hook payload, or return an empty mapping if it is not a JSON object."""
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return document if isinstance(document, dict) else {}


def target_path(payload: str) -> Path | None:
    """Extract the edited file path from a hook payload, or None if absent or malformed."""
    tool_input = parse_payload(payload).get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            return Path(raw)
    return None


def notice(event: str, context: str, user_message: str | None = None) -> str:
    """Return the JSON a hook prints on stdout to tell Claude something without blocking.

    `context` reaches the model as a system reminder; `user_message`, when given, is shown to the
    person as a warning. Both are capped at 10,000 characters by Claude Code. Exit 0 with this on
    stdout: exit 2 would turn it into a block.
    """
    document: dict[str, object] = {
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
    }
    if user_message is not None:
        document["systemMessage"] = user_message
    return json.dumps(document)


def find_repo_root(start: Path | None = None) -> Path | None:
    """Return the nearest ancestor containing a `.git` entry, or None if there is none."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def inside_repo(target: Path, root: Path) -> bool:
    """Return whether `target` lies within `root`.

    Delegates to `pathlib`, which compares case-insensitively and separator-agnostically on
    Windows and case-sensitively on POSIX. That is the correct rule on each platform, and
    getting it right is why these hooks are Python rather than shell.
    """
    return target.resolve().is_relative_to(root.resolve())


def owning_repo(target: Path, session_root: Path) -> Path | None:
    """Return the repository holding `target`, or None if it is not within `session_root`.

    The hooks run from the session's project root, so `session_root` says which files are this
    session's business — a scratchpad, memory, or a sibling repository are not. Walking up from
    the *file* to find its repository, rather than taking `session_root` as the answer, is what
    keeps a linked worktree under the project correct: its `.git` pointer is nearer than the
    main checkout's, and its branch is the one being edited.
    """
    repo = find_repo_root(target.parent)
    if repo is None or not inside_repo(repo, session_root):
        return None
    return repo


GATE_CONFIG_NAMES = ("prek.toml", ".pre-commit-config.yaml")


def _has_gate_config(directory: Path) -> bool:
    """Return whether `directory` holds a prek configuration file."""
    return any((directory / name).exists() for name in GATE_CONFIG_NAMES)


def find_gate_root(target: Path, root: Path) -> Path | None:
    """Return the nearest ancestor of `target` holding a prek config, bounded by `root`.

    In a generated project the config sits at the repository root, so this returns `root` and
    the gate behaves exactly as it did when that root was hard-coded. In this template repo the
    project lives one level down under `template/`, and the answer is that subdirectory — which
    is why the hook needs to search rather than assume.

    None means no config governs the file. The caller lets the edit stand rather than blocking,
    because a directory outside any project — this repo's own root, holding only markdown — is a
    legitimate place to edit.
    """
    resolved_root = root.resolve()
    for candidate in [target.resolve().parent, *target.resolve().parents]:
        if not candidate.is_relative_to(resolved_root):
            return None
        if _has_gate_config(candidate):
            return candidate
    return None
