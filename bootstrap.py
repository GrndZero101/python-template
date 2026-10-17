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
    sh bootstrap.sh setup           # install or upgrade the uv tools, write copier's settings

bootstrap.sh has already made sure of a standalone uv at or above its pin, so nothing here checks
that again. Stdlib only, so there is nothing to download on a bare machine.
"""

import argparse
import difflib
import json
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

SETTINGS_HEADER = (
    "# Written by `sh bootstrap.sh setup`, from git's identity. copier uses these as the default\n"
    "# answer to every template question of the same name, in place of the template's own.\n"
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `command` and capture its output. Never a shell string."""
    logger.debug("running %s", command)
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def _confirm(question: str) -> bool:
    """Ask `question` on stderr, which leaves stdout to the report, and read a yes or no."""
    sys.stderr.write(f"bootstrap: {question}? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


@dataclass(frozen=True)
class Probe:
    """Everything the helper reads from the machine, or asks its user, so a test can fake it."""

    run: Runner = _run
    which: Callable[[str], str | None] = shutil.which
    env: Mapping[str, str] = field(default_factory=os.environ.copy)
    home: Path = field(default_factory=Path.home)
    system: str = field(default_factory=platform.system)
    confirm: Callable[[str], bool] = _confirm
    interactive: bool = field(default_factory=sys.stdin.isatty)


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


def upgrade_uv_tools(probe: Probe) -> bool:
    """Install each of UV_TOOLS that is missing and upgrade the rest. Return whether all worked."""
    listed = probe.run(["uv", "tool", "list"])
    installed = parse_tool_list(listed.stdout) if listed.returncode == 0 else {}
    all_ok = True
    for name in UV_TOOLS:
        verb = "upgrade" if name in installed else "install"
        logger.info("uv tool %s %s", verb, name)
        completed = probe.run(["uv", "tool", verb, name])
        if completed.returncode != 0:
            logger.error("uv tool %s %s failed: %s", verb, name, completed.stderr.strip())
            all_ok = False
    return all_ok


def git_config(probe: Probe, key: str) -> str:
    """Return git's value for `key`, or "" when git is missing or the key is unset."""
    if probe.which("git") is None:
        return ""
    completed = probe.run(["git", "config", "--get", key])
    return completed.stdout.strip() if completed.returncode == 0 else ""


def noreply_email(probe: Probe) -> str | None:
    """Return the GitHub noreply address of gh's logged-in user, or None without one.

    Built from the account's id and login, which gh's default token can read: the account's own
    email it cannot, when that is private.
    """
    if probe.which("gh") is None:
        return None
    completed = probe.run(["gh", "api", "user"])
    if completed.returncode != 0:
        return None
    user = json.loads(completed.stdout)
    return f"{user['id']}+{user['login']}@users.noreply.github.com"


def choose_email(probe: Probe, git_email: str, *, noreply: bool) -> str:
    """Return git's email, or the GitHub noreply address when asked for it or agreed to."""
    private = noreply_email(probe)
    if private is None or private == git_email:
        return git_email
    if noreply:
        return private
    if probe.interactive and probe.confirm(
        f"Use your GitHub noreply address {private} instead of {git_email or 'no email'}"
    ):
        return private
    logger.info("using %s; setup --noreply would use %s", git_email or "no email", private)
    return git_email


def settings_text(name: str, email: str) -> str:
    """Return copier's settings file answering the author questions.

    YAML, written without a YAML library: a JSON string is a valid YAML double-quoted scalar.
    """
    return (
        f"{SETTINGS_HEADER}defaults:\n"
        f"  author_name: {json.dumps(name)}\n"
        f"  author_email: {json.dumps(email)}\n"
    )


def write_settings(probe: Probe, path: Path, text: str, *, assume_yes: bool) -> bool:
    """Write `text` to `path`, showing the diff and asking before replacing anything there.

    Return False only when consent was needed and there was no way to ask; a "no" is an answer.
    """
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    if old == text:
        logger.info("copier settings unchanged: %s", path)
        return True
    if old is not None:
        diff = difflib.unified_diff(
            old.splitlines(keepends=True), text.splitlines(keepends=True), str(path), "new"
        )
        sys.stderr.writelines(diff)
        if not assume_yes and not probe.interactive:
            logger.error("replacing %s needs consent; rerun as: sh bootstrap.sh --yes setup", path)
            return False
        if not assume_yes and not probe.confirm(f"Replace {path} as above"):
            logger.info("left %s as it was", path)
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.info("wrote copier settings: %s", path)
    return True


def setup(probe: Probe, *, assume_yes: bool, noreply: bool) -> bool:
    """Install or upgrade the uv tools and write copier's settings. Return whether all worked."""
    tools_ok = upgrade_uv_tools(probe)
    name = git_config(probe, "user.name")
    if not name:
        logger.error('no copier settings without a name: git config --global user.name "..."')
        return False
    email = choose_email(probe, git_config(probe, "user.email"), noreply=noreply)
    path = copier_settings_path(probe.env, probe.home, probe.system)
    settings_ok = write_settings(probe, path, settings_text(name, email), assume_yes=assume_yes)
    return tools_ok and settings_ok


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
    setup_parser = commands.add_parser(
        "setup", help="install or upgrade copier and prek, and write copier's settings"
    )
    setup_parser.add_argument(
        "--noreply",
        action="store_true",
        help="answer author_email with your GitHub noreply address",
    )
    return parser


def main(argv: list[str] | None = None, probe: Probe | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    # force: basicConfig is a no-op once a handler exists, and a test calls main more than once.
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(levelname)s %(message)s", force=True
    )
    probe = probe or Probe()
    done = True
    if args.command == "setup":
        done = setup(probe, assume_yes=args.yes, noreply=args.noreply)
    # setup ends with doctor's report too, so a run shows what it left.
    checks = doctor(probe)
    sys.stdout.write(render(checks))
    failed = [check.name for check in checks if check.required and not check.ok]
    if failed:
        logger.error("not ready: %s", ", ".join(failed))
    if failed or not done:
        return NOT_READY
    return 0


if __name__ == "__main__":
    sys.exit(main())
