"""Shared parsing for Claude Code hook payloads.

Both `branch_guard` and `gate` are handed the same JSON on stdin and both need the same two
answers from it: which file is being touched, and where the repository root is. That logic
lives here so the two hooks cannot drift apart.

Every function fails soft — a malformed payload yields None rather than raising. A hook that
crashes on unexpected input would block every edit in the session, which is worse than the
check it was performing.
"""

import json
from pathlib import Path


def target_path(payload: str) -> Path | None:
    """Extract the edited file path from a hook payload, or None if absent or malformed."""
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return None
    tool_input = document.get("tool_input") if isinstance(document, dict) else None
    raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return Path(raw) if isinstance(raw, str) and raw else None


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
