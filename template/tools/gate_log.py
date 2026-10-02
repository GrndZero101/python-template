"""Append one line per gate run to `.gate.log`, so a benchmark can count blocks per task.

Both `gate` (after every edit) and `stop_gate` (before a turn ends) write here. Each line is one
JSON object:

    {"at": "2026-10-02T09:15:00+00:00", "hook": "gate", "outcome": "block",
     "failed": ["ruff-check"], "target": "src/pkg/x.py"}

`outcome` is one of `pass`, `fixed` (failed only on prek's own auto-fixes and passed when re-run),
`block`, `paused` (conflict markers present) and `skipped` (prek could not run). The file sits at
the gate root and is gitignored. Writing it never blocks an edit: a failure is reported on stderr
and the hook carries on.
"""

import dataclasses
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

LOG_NAME = ".gate.log"
# prek prints this line under every hook it reports as failed; with `--quiet` it reports no others.
HOOK_ID_LINE = re.compile(r"^- hook id: (\S+)$", re.MULTILINE)

Outcome = Literal["pass", "fixed", "block", "paused", "skipped"]


@dataclasses.dataclass(frozen=True)
class Entry:
    """One gate run, as it is logged."""

    hook: str
    outcome: Outcome
    target: str
    failed: tuple[str, ...] = ()


def failed_hooks(output: str) -> tuple[str, ...]:
    """Return the ids of the hooks prek reported in `output`, in the order it reported them."""
    return tuple(HOOK_ID_LINE.findall(output))


def _utc_now() -> datetime:
    """Return the current time. The default clock; tests pass their own."""
    return datetime.now(UTC)


def record(root: Path, entry: Entry, now: Callable[[], datetime] = _utc_now) -> None:
    """Append `entry` to `root/.gate.log`, reporting on stderr rather than raising if it cannot."""
    fields = dataclasses.asdict(entry)
    fields["failed"] = list(entry.failed)
    line = json.dumps({"at": now().isoformat(timespec="seconds"), **fields})
    try:
        with (root / LOG_NAME).open("a", encoding="utf-8") as log:
            log.write(f"{line}\n")
    except OSError as exc:
        sys.stderr.write(f"gate log not written to {root / LOG_NAME}: {exc}\n")
