# /// script
# requires-python = ">=3.14"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-10-17T00:00:00Z"
# ///
"""Get a machine ready for this template.

Run it through the shim, never directly:

    sh bootstrap.sh doctor          # report what is installed and configured; change nothing

bootstrap.sh has already made sure of a standalone uv at or above its pin, so nothing here checks
that again. Stdlib only, so there is nothing to download on a bare machine.
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)
NOT_READY = 1

# The uv tools a project's workflow runs: copier to generate and update, prek for the gate.
UV_TOOLS = ("copier", "prek")

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `command` and capture its output. Never a shell string."""
    logger.debug("running %s", command)
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


@dataclass(frozen=True)
class Probe:
    """Everything `doctor` reads from the machine, so a test can hand it another one."""

    run: Runner = _run
    which: Callable[[str], str | None] = shutil.which
    env: Mapping[str, str] = field(default_factory=os.environ.copy)
    home: Path = field(default_factory=Path.home)
    system: str = field(default_factory=platform.system)


@dataclass(frozen=True)
class Check:
    """One line of the report. A check that is not `required` is advice, and cannot fail it."""

    name: str
    ok: bool
    detail: str
    required: bool = True


def parse_tool_list(text: str) -> dict[str, str]:
    """Return {name: version} from `uv tool list`, whose tools are lines like `copier v9.18.2`."""
    tools: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith(("-", " ")):
            continue  # an executable the tool above installed, or a blank line
        name, _, rest = line.partition(" ")
        version = rest.split(maxsplit=1)[0] if rest else ""
        tools[name] = version.removeprefix("v")
    return tools


def copier_settings_path(env: Mapping[str, str], home: Path, system: str) -> Path:
    """Return where copier reads its settings: COPIER_SETTINGS_PATH, else the platform's default."""
    override = env.get("COPIER_SETTINGS_PATH")
    if override:
        return Path(override)
    if system == "Darwin":
        root = home / "Library" / "Application Support"
    elif system == "Windows":
        root = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
    else:
        root = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    return root / "copier" / "settings.yml"


def check_uv(probe: Probe) -> Check:
    """Report the running uv's version. The shim has already held it to the pin."""
    completed = probe.run(["uv", "self", "version", "--short"])
    if completed.returncode != 0:
        return Check("uv", ok=False, detail=f"`uv self version` failed: {completed.stderr.strip()}")
    return Check("uv", ok=True, detail=completed.stdout.strip())


def check_uv_tools(probe: Probe) -> list[Check]:
    """Report copier and prek, which must be uv tools rather than anything else on PATH."""
    completed = probe.run(["uv", "tool", "list"])
    if completed.returncode != 0:
        detail = f"`uv tool list` failed: {completed.stderr.strip()}"
        return [Check(name, ok=False, detail=detail) for name in UV_TOOLS]
    installed = parse_tool_list(completed.stdout)
    checks: list[Check] = []
    for name in UV_TOOLS:
        version = installed.get(name)
        if version is None:
            checks.append(Check(name, ok=False, detail=f"not a uv tool: uv tool install {name}"))
        else:
            checks.append(Check(name, ok=True, detail=version))
    return checks


def check_git_identity(probe: Probe) -> list[Check]:
    """Report git's user.name and user.email, which every generated project commits as."""
    if probe.which("git") is None:
        return [Check("git", ok=False, detail="git is not installed")]
    checks: list[Check] = []
    for key in ("user.name", "user.email"):
        completed = probe.run(["git", "config", "--get", key])
        value = completed.stdout.strip()
        if completed.returncode != 0 or not value:
            fix = f'not set: git config --global {key} "..."'
            checks.append(Check(f"git {key}", ok=False, detail=fix))
        else:
            checks.append(Check(f"git {key}", ok=True, detail=value))
    return checks


def check_copier_settings(probe: Probe) -> Check:
    """Report copier's settings file, whose defaults answer the author questions. Advice only."""
    path = copier_settings_path(probe.env, probe.home, probe.system)
    if path.is_file():
        return Check("copier settings", ok=True, detail=str(path), required=False)
    detail = f"none at {path}, so copier asks for your name and email every time"
    return Check("copier settings", ok=False, detail=detail, required=False)


def check_gh(probe: Probe) -> Check:
    """Report the GitHub CLI and its login. Advice only: nothing needs it, it offers a noreply email."""
    if probe.which("gh") is None:
        return Check("gh", ok=False, detail="not installed (optional)", required=False)
    completed = probe.run(["gh", "auth", "status"])
    if completed.returncode != 0:
        return Check("gh", ok=False, detail="not logged in: gh auth login", required=False)
    return Check("gh", ok=True, detail="logged in", required=False)


def doctor(probe: Probe) -> list[Check]:
    """Run every check, changing nothing, in the order the report shows them."""
    if probe.which("uv") is None:
        checks = [Check("uv", ok=False, detail="not on PATH: run this as sh bootstrap.sh doctor")]
    else:
        checks = [check_uv(probe), *check_uv_tools(probe)]
    checks.extend(check_git_identity(probe))
    checks.append(check_copier_settings(probe))
    checks.append(check_gh(probe))
    return checks


def render(checks: list[Check]) -> str:
    """Return the report: one aligned line per check, `ok`, `FAIL`, or `warn` for advice."""
    width = max(len(check.name) for check in checks)
    lines: list[str] = []
    for check in checks:
        if check.ok:
            status = "ok"
        elif check.required:
            status = "FAIL"
        else:
            status = "warn"
        lines.append(f"{status:<5}{check.name:<{width}}  {check.detail}")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="bootstrap.sh", description="Get a machine ready for this template."
    )
    # The shim reads --yes too, so it goes first, before the command, for both to see it.
    parser.add_argument("--yes", action="store_true", help="agree to every change without asking")
    parser.add_argument("-v", "--verbose", action="store_true", help="log at DEBUG level")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="report what is installed and configured; change nothing")
    return parser


def main(argv: list[str] | None = None, probe: Probe | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    # force: basicConfig is a no-op once a handler exists, and a test calls main more than once.
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(levelname)s %(message)s", force=True
    )
    checks = doctor(probe or Probe())
    sys.stdout.write(render(checks))
    failed = [check.name for check in checks if check.required and not check.ok]
    if failed:
        logger.error("not ready: %s", ", ".join(failed))
        return NOT_READY
    return 0


if __name__ == "__main__":
    sys.exit(main())
