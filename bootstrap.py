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
    sh bootstrap.sh new my-project  # generate a project from the CLI template, once doctor passes
    sh bootstrap.sh update my-project  # update both layers, committed on chore/template-update
    sh bootstrap.sh pins            # show the uv pin beside uv's latest release
    sh bootstrap.sh pins --update uv  # move the pin everywhere it is written, here and in the CLI repo

bootstrap.sh has already made sure of a standalone uv at or above its pin, so nothing here checks
that again. Stdlib only, so there is nothing to download on a bare machine.
"""

import argparse
import difflib
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)
FAILED = 1
HERE = Path(__file__).resolve().parent

# The uv tools a project's workflow runs: copier to generate and update, prek for the gate.
UV_TOOLS = ("copier", "prek")

# What `new` copies: the CLI use case, which applies the base to the same directory itself.
CLI_TEMPLATE = "gh:GrndZero101/python-template-cli-typer"

# The latest uv release, from PyPI's JSON API, which needs no token.
UV_RELEASES = "https://pypi.org/pypi/uv/json"

# The CLI template's clone, which holds copies of the uv pin too. By default, beside this one.
CLI_REPO_NAME = "python-template-cli-typer"

# A version as uv numbers its releases: dot-separated numbers and nothing else.
VERSION = re.compile(r"^\d+(\.\d+)*$")

SETTINGS_HEADER = (
    "# Written by `sh bootstrap.sh setup`, from git's identity. copier uses these as the default\n"
    "# answer to every template question of the same name, in place of the template's own.\n"
)


class Runner(Protocol):
    """Runs a command and captures its output. `env`, when given, is the whole environment."""

    def __call__(
        self, command: list[str], env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run `command`."""
        ...


def _run(
    command: list[str], env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `command` and capture its output. Never a shell string."""
    logger.debug("running %s", command)
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)  # noqa: S603


class Attacher(Protocol):
    """Runs a command at the terminal and returns its exit code. `env` is as for a Runner."""

    def __call__(self, command: list[str], env: Mapping[str, str] | None = None) -> int:
        """Run `command`."""
        ...


def _attach(command: list[str], env: Mapping[str, str] | None = None) -> int:
    """Run `command` at the terminal, for the questions it asks, and return its exit code.

    Its stdout goes to stderr, which is still the terminal, so the helper's own stdout stays data.
    """
    logger.debug("running %s", command)
    return subprocess.run(command, stdout=sys.stderr, check=False, env=env).returncode  # noqa: S603


def _fetch(url: str) -> bytes:
    """Return the body at `url`."""
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 -- constant https URLs
        return response.read()


def _confirm(question: str) -> bool:
    """Ask `question` on stderr, which leaves stdout to the report, and read a yes or no."""
    sys.stderr.write(f"bootstrap: {question}? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


@dataclass(frozen=True)
class Probe:
    """Everything the helper reads from the machine, or asks its user, so a test can fake it."""

    run: Runner = _run
    attach: Attacher = _attach
    which: Callable[[str], str | None] = shutil.which
    env: Mapping[str, str] = field(default_factory=os.environ.copy)
    home: Path = field(default_factory=Path.home)
    system: str = field(default_factory=platform.system)
    confirm: Callable[[str], bool] = _confirm
    interactive: bool = field(default_factory=sys.stdin.isatty)
    fetch: Callable[[str], bytes] = _fetch


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


def _occupied(path: Path) -> bool:
    """Return whether `path` is a file, or a directory with anything in it."""
    return path.exists() and (not path.is_dir() or any(path.iterdir()))


def _ready_for_copier(probe: Probe) -> bool:
    """Return whether doctor passes and copier is on PATH, saying what to do when not.

    The report goes to stderr: the commands that check this keep stdout for their own data.
    """
    checks = doctor(probe)
    failed = failed_checks(checks)
    if failed:
        sys.stderr.write(render(checks))
        logger.error("not ready (%s): run sh bootstrap.sh setup first", ", ".join(failed))
        return False
    if probe.which("copier") is None:
        logger.error("copier is not on PATH: run uv tool update-shell, then open a new shell")
        return False
    return True


def new(probe: Probe, destination: Path, *, template: str, copier_args: list[str]) -> bool:
    """Generate a project at `destination` with copier, once doctor passes. Return whether it did."""
    if not _ready_for_copier(probe):
        return False
    if _occupied(destination):
        logger.error("%s is already there and not an empty directory; name a new one", destination)
        return False
    command = ["copier", "copy", "--trust", *copier_args, template, str(destination)]
    returncode = probe.attach(command)
    if returncode != 0:
        logger.error("copier copy exited %d; its error is above", returncode)
        return False
    return True


@dataclass(frozen=True)
class PinSite:
    """One place a pin is written: a file in its repo, and a pattern whose `version` group is it.

    An `at_least` site may run ahead of the pin, and is moved only when it would fall below it.
    """

    path: str
    pattern: re.Pattern[str]
    at_least: bool = False


SHIM_PIN = re.compile(r"^UV_VERSION=(?P<version>\S+)\r?$", re.MULTILINE)
_UV_FLOOR = re.compile(r'^required-version = ">=(?P<version>[^"]+)"\r?$', re.MULTILINE)
_SETUP_UV = re.compile(r'^\s+version: "(?P<version>[^"]+)"\r?$', re.MULTILINE)
# uv-pre-commit's uv-lock hook runs the uv of its own rev, which the floor stops below the pin.
_UV_HOOK = re.compile(r"/uv-pre-commit\r?\n\s+rev: v?(?P<version>\d+(?:\.\d+)*)\r?$", re.MULTILINE)

# Every copy of the uv pin, which a test in each repo holds to the shim's line. A copy added
# without a line here fails that test the first time the pin moves.
BASE_UV_SITES = (
    PinSite("bootstrap.sh", SHIM_PIN),
    PinSite("pyproject.toml", _UV_FLOOR),
    PinSite("template/pyproject.toml.jinja", _UV_FLOOR),
    PinSite(".github/workflows/ci.yml", _SETUP_UV),
    PinSite("template/.pre-commit-config.yaml.jinja", _UV_HOOK, at_least=True),
)
CLI_UV_SITES = (
    PinSite("pyproject.toml", _UV_FLOOR),
    PinSite("template/pyproject.toml.jinja", _UV_FLOOR),
    PinSite(".github/workflows/ci.yml", _SETUP_UV),
)

PIN_COMMIT_BODY = (
    "Moved by `sh bootstrap.sh pins --update uv`. The generation suite was skipped at this\n"
    "commit: finish_branch.py runs it, and trusts no hook."
)


PIN_NEXT_STEPS = """
Next, in this order:
  1. here:        uv run python template/tools/finish_branch.py --no-tests && git push
  2. in {cli}:
       BASE_TEMPLATE_DIR={base} uv run python {base}/template/tools/finish_branch.py --no-tests
       git push
  3. here: this repo's CI ran the CLI repo's suite before step 2 landed, so it failed on the pin;
     gh run rerun <id> --failed
"""


def version_key(version: str) -> tuple[int, ...]:
    """Return `version` as numbers, so that 0.13.0 sorts above 0.9.0."""
    return tuple(int(part) for part in version.split("."))


def read_pin(root: Path) -> str:
    """Return the uv pin: the shim's UV_VERSION line."""
    shim = root / "bootstrap.sh"
    found = SHIM_PIN.search(shim.read_text(encoding="utf-8"))
    if found is None:
        message = f"no UV_VERSION= line in {shim}; restore it from git"
        raise ValueError(message)
    return found["version"]


def latest_uv(probe: Probe) -> str:
    """Return the newest uv release on PyPI."""
    return json.loads(probe.fetch(UV_RELEASES))["info"]["version"]


def pin_checks(probe: Probe, root: Path) -> list[Check]:
    """Report each pin beside its latest release. Advice only: a pin is a floor, not a lag."""
    pin = read_pin(root)
    try:
        latest = latest_uv(probe)
    except OSError, ValueError, KeyError:
        logger.exception("could not read uv's latest release from %s", UV_RELEASES)
        return [Check("uv", ok=False, detail=f"{pin}, latest unknown", required=False)]
    if version_key(pin) >= version_key(latest):
        return [Check("uv", ok=True, detail=f"{pin}, the latest")]
    detail = f"{pin}, latest {latest}: sh bootstrap.sh pins --update uv"
    return [Check("uv", ok=False, detail=detail, required=False)]


def rewrite_pin(text: str, site: PinSite, old: str, new: str) -> str | None:
    """Return `text` with every match of the site's pattern moved from `old` to `new`.

    An `at_least` site's matches are moved only when below `new`. Otherwise, None when nothing
    matches or a match holds anything but `old`: the copies already disagree, which is for a
    person to sort out, not for this to paper over.
    """
    matches = list(site.pattern.finditer(text))
    if not matches:
        return None
    if site.at_least:
        matches = [match for match in matches if version_key(match["version"]) < version_key(new)]
    elif any(match["version"] != old for match in matches):
        return None
    pieces: list[str] = []
    end = 0
    for match in matches:
        start, stop = match.span("version")
        pieces.extend((text[end:start], new))
        end = stop
    pieces.append(text[end:])
    return "".join(pieces)


def plan_move(root: Path, sites: tuple[PinSite, ...], old: str, new: str) -> dict[Path, str] | None:
    """Return each site's file under `root` with the pin moved, or None if one does not hold it."""
    files: dict[Path, str] = {}
    for site in sites:
        path = root / site.path
        # newline="": a file is written back with the line endings it was read with.
        text = path.read_text(encoding="utf-8", newline="") if path.is_file() else ""
        moved = rewrite_pin(text, site, old, new)
        if moved is None:
            logger.error("%s does not hold the uv pin %s; make every copy agree first", path, old)
            return None
        files[path] = moved
    return files


def _git(
    probe: Probe, root: Path, *args: str, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git in `root`."""
    return probe.run(["git", "-C", str(root), *args], env)


def _clean_checkout(probe: Probe, root: Path) -> bool:
    """Return whether `root` is a git checkout with nothing uncommitted, saying why not."""
    completed = _git(probe, root, "status", "--porcelain")
    if completed.returncode != 0:
        logger.error("%s is not a git checkout: %s", root, completed.stderr.strip())
        return False
    if completed.stdout.strip():
        logger.error("%s has uncommitted changes; commit or stash them first", root)
        return False
    return True


def commit_move(probe: Probe, root: Path, files: dict[Path, str], new: str) -> bool:
    """Write `files` on a new branch from main in `root`, and commit them there."""
    branch = f"build/uv-{new}"
    switched = _git(probe, root, "switch", "--create", branch, "main")
    if switched.returncode != 0:
        logger.error("%s: git switch failed: %s", root, switched.stderr.strip())
        return False
    for path, text in files.items():
        path.write_text(text, encoding="utf-8", newline="")
    # Staged by name, never `commit --all`: that hands the hooks a temporary GIT_INDEX_FILE, which
    # every git they run inherits, in whatever repo it is run.
    staged = _git(probe, root, "add", "--", *(str(path.relative_to(root)) for path in files))
    if staged.returncode != 0:
        logger.error("%s: git add failed: %s", root, staged.stderr.strip())
        return False
    # The CLI repo's suite would test against the base on GitHub, whose pin has not moved yet.
    env = {**probe.env, "SKIP": "generation-tests"}
    message = f"build(uv): raise the uv floor to {new}"
    committed = _git(probe, root, "commit", "-m", message, "-m", PIN_COMMIT_BODY, env=env)
    if committed.returncode != 0:
        output = (committed.stdout + committed.stderr).strip()
        logger.error(
            "%s: the commit on %s failed, its changes left in place: %s", root, branch, output
        )
        return False
    logger.info("%s: committed on %s", root, branch)
    return True


def resolve_target(probe: Probe, old: str, requested: str | None) -> str | None:
    """Return the version to move the uv pin to, `old` itself when it is there already, or None."""
    try:
        new = requested or latest_uv(probe)
    except OSError, ValueError, KeyError:
        logger.exception(
            "could not read uv's latest release from %s; name one with --to", UV_RELEASES
        )
        return None
    if not VERSION.match(new):
        logger.error("--to %s is not a version; name one like %s", new, old)
        return None
    if version_key(new) < version_key(old):
        logger.error("%s is below the pin %s, and a floor only rises", new, old)
        return None
    return new


def uv_reaches(probe: Probe, new: str) -> bool:
    """Return whether the running uv is at or above `new`, saying what to do when it is not.

    A floor above the running uv stops every `uv run` in both repos, the commit's own hooks first.
    """
    running = check_uv(probe)
    if not running.ok:
        logger.error("uv: %s", running.detail)
        return False
    if version_key(running.detail) < version_key(new):
        logger.error("uv %s is below %s: run uv self update %s first", running.detail, new, new)
        return False
    return True


def move_uv(probe: Probe, base: Path, cli: Path, new: str) -> bool:
    """Move the uv pin to `new` in this repo and the CLI repo, committed on a branch in each.

    Nothing changes until both checkouts are clean and every copy holds the current pin.
    """
    old = read_pin(base)
    repos = ((base, BASE_UV_SITES), (cli, CLI_UV_SITES))
    if not all(_clean_checkout(probe, root) for root, _ in repos):
        return False
    plans: list[tuple[Path, dict[Path, str]]] = []
    for root, sites in repos:
        files = plan_move(root, sites, old, new)
        if files is None:
            return False
        plans.append((root, files))
    for root, files in plans:
        if not commit_move(probe, root, files, new):
            return False
    sys.stderr.write(PIN_NEXT_STEPS.format(base=base, cli=cli))
    return True


def _pins(probe: Probe, root: Path, args: argparse.Namespace) -> int:
    """Run `pins`: the report, or with --update, the move."""
    if args.update is None:
        sys.stdout.write(render(pin_checks(probe, root)))
        return 0
    cli = args.cli_repo or root.parent / CLI_REPO_NAME
    if not cli.is_dir():
        logger.error("no CLI template clone at %s; name it with --cli-repo", cli)
        return FAILED
    old = read_pin(root)
    new = resolve_target(probe, old, args.to)
    if new is None:
        return FAILED
    if new == old:
        logger.info("the uv pin is %s already", old)
        return 0
    if not uv_reaches(probe, new):
        return FAILED
    return 0 if move_uv(probe, root, cli.resolve(), new) else FAILED


# What `update` brings up to date, in this order: the use case, then the base under it. A project
# generated from the base alone has only the second.
ANSWERS_FILES = (".copier-answers.yml", ".copier-answers.base.yml")
UPDATE_BRANCH = "chore/template-update"
UPDATE_SUMMARY = "chore(template): update from the templates"
# The two keys read from an answers file are plain scalars, so there is no YAML library to need.
_ANSWER = re.compile(r"^(?P<key>_commit|_src_path): (?P<value>.+?)\r?$", re.MULTILINE)

UPDATE_RESUME = """
To carry on, in {project}:
  1. {first}
  2. uv sync && git add -A && git commit -m "{message}"
  3. {rerun}
"""

UPDATE_NEXT_STEPS = """
Committed on {branch} in {project}. Review it: git diff main. A new key in an answers file is a
question copier answered for you. Then finish it, which squashes, gates, tests and merges:
  cd {project} && uv run python tools/finish_branch.py "{summary}"
or rerun with --finish to have this run it.
"""


@dataclass(frozen=True)
class Layer:
    """One template a project was generated from, as its answers file records it."""

    answers: str
    source: str
    commit: str

    @property
    def name(self) -> str:
        """Return the template's repository name, the last part of its source."""
        if not self.source:
            return self.answers
        return re.split(r"[/\\]", self.source.rstrip("/\\"))[-1].removesuffix(".git")


@dataclass(frozen=True)
class UpdateRun:
    """What one `update` was asked to do, which a run resumed after a stop repeats."""

    project: Path
    copier_args: tuple[str, ...] = ()
    finish: bool = False

    def rerun(self) -> str:
        """Return the command that carries on where this run stopped."""
        command = ["sh", str(HERE / "bootstrap.sh"), "update", str(self.project)]
        if self.finish:
            command.append("--finish")
        if self.copier_args:
            command.extend(["--", *self.copier_args])
        return shlex.join(command)


def read_layer(project: Path, answers: str) -> Layer | None:
    """Return the layer that `answers` records in `project`, or None when there is no such file."""
    path = project / answers
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    found = {match["key"]: match["value"].strip("'\"") for match in _ANSWER.finditer(text)}
    return Layer(answers, found.get("_src_path", ""), found.get("_commit", ""))


def _branch(probe: Probe, root: Path) -> str:
    """Return the branch checked out in `root`, or "" when there is none."""
    completed = _git(probe, root, "branch", "--show-current")
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _on_update_branch(probe: Probe, project: Path) -> bool:
    """Move onto UPDATE_BRANCH from main, taking the working tree along, unless it is there already.

    Left until there is something to commit, so an update that changes nothing leaves no branch.
    """
    if _branch(probe, project) == UPDATE_BRANCH:
        return True
    switched = _git(probe, project, "switch", "--create", UPDATE_BRANCH)
    if switched.returncode != 0:
        logger.error("%s: git switch failed: %s", project, switched.stderr.strip())
        return False
    logger.info("%s: on a new branch, %s", project, UPDATE_BRANCH)
    return True


def _layers_to_update(probe: Probe, project: Path) -> list[Layer] | None:
    """Return the project's layers in update order, or None when it cannot be updated now."""
    if not _ready_for_copier(probe) or not _clean_checkout(probe, project):
        return None
    branch = _branch(probe, project)
    if branch not in {"main", UPDATE_BRANCH}:
        logger.error(
            "%s is on %s: switch to main first; update makes its own branch", project, branch
        )
        return None
    layers: list[Layer] = []
    for answers in ANSWERS_FILES:
        layer = read_layer(project, answers)
        if layer is not None:
            layers.append(layer)
    if not layers:
        names = " or ".join(ANSWERS_FILES)
        logger.error("%s has no %s: it was not generated from these templates", project, names)
        return None
    return layers


def _project_env(probe: Probe) -> dict[str, str]:
    """Return the environment for a command that runs uv in the project, the commit's hooks too.

    `uv run --script` points VIRTUAL_ENV at the helper's own environment, and every uv run in the
    project would warn that it ignores it.
    """
    return {name: value for name, value in probe.env.items() if name != "VIRTUAL_ENV"}


def _stop(run: UpdateRun, layer: Layer, first: str) -> None:
    """Log how to carry on after this layer stopped part way, its changes left in place."""
    moved = read_layer(run.project, layer.answers) or layer
    message = f"chore(template): update {layer.name} to {moved.commit}"
    resume = UPDATE_RESUME.format(
        project=run.project, first=first, message=message, rerun=run.rerun()
    )
    sys.stderr.write(resume)


def _commit_layer(probe: Probe, run: UpdateRun, layer: Layer) -> Check:
    """Commit what updating `layer` changed, on UPDATE_BRANCH."""
    moved = read_layer(run.project, layer.answers) or layer
    if not _on_update_branch(probe, run.project):
        return Check(layer.name, ok=False, detail=f"could not switch to {UPDATE_BRANCH}")
    # Added, then committed: never `commit --all`, which hands the hooks a temporary index.
    staged = _git(probe, run.project, "add", "--all")
    if staged.returncode != 0:
        return Check(layer.name, ok=False, detail=f"git add failed: {staged.stderr.strip()}")
    message = f"chore(template): update {layer.name} to {moved.commit}"
    committed = _git(probe, run.project, "commit", "-m", message, env=_project_env(probe))
    if committed.returncode != 0:
        logger.error("the commit failed: %s", (committed.stdout + committed.stderr).strip())
        _stop(run, layer, "fix what the commit's hooks reported above")
        return Check(layer.name, ok=False, detail="the commit failed; its hooks' output is above")
    return Check(layer.name, ok=True, detail=f"{layer.commit} -> {moved.commit}")


def update_layer(probe: Probe, run: UpdateRun, layer: Layer) -> Check:
    """Bring one layer up to date and commit it. A failed check means stop here."""
    logger.info("%s: copier update from %s", layer.name, layer.commit)
    command = ["copier", "update", "--trust", "-a", layer.answers, *run.copier_args]
    returncode = probe.attach([*command, str(run.project)])
    if returncode != 0:
        detail = f"copier update exited {returncode}; its error is above, git status what it left"
        return Check(layer.name, ok=False, detail=detail)
    # copier exits 0 on a conflict: it writes the markers and records each file as unmerged.
    conflicts = _git(probe, run.project, "diff", "--name-only", "--diff-filter=U")
    if conflicts.stdout.strip():
        _on_update_branch(probe, run.project)  # so the commit that resolves them lands off main
        _stop(run, layer, 'resolve each conflict, then git add it (README: "Conflicts")')
        detail = f"conflicts in {', '.join(conflicts.stdout.splitlines())}"
        return Check(layer.name, ok=False, detail=detail)
    # Before anything checks the update: a dependency the template dropped is still in .venv.
    synced = probe.run(["uv", "sync", "--directory", str(run.project)], _project_env(probe))
    if synced.returncode != 0:
        _stop(run, layer, "fix what uv sync reported")
        return Check(layer.name, ok=False, detail=f"uv sync failed: {synced.stderr.strip()}")
    if not _git(probe, run.project, "status", "--porcelain").stdout.strip():
        return Check(layer.name, ok=True, detail=f"already at {layer.commit}")
    return _commit_layer(probe, run, layer)


def update(probe: Probe, run: UpdateRun, layers: list[Layer]) -> list[Check]:
    """Update each layer in turn, stopping at the first that does not finish cleanly."""
    checks: list[Check] = []
    for layer in layers:
        check = update_layer(probe, run, layer)
        checks.append(check)
        if not check.ok:
            break
    return checks


def finish_update(probe: Probe, project: Path) -> bool:
    """Run the project's finish_branch.py on UPDATE_BRANCH, which merges it into main."""
    command = ["uv", "run", "--directory", str(project), "python", "tools/finish_branch.py"]
    returncode = probe.attach([*command, UPDATE_SUMMARY], _project_env(probe))
    if returncode != 0:
        logger.error("finish_branch.py exited %d; its output above says what to do", returncode)
        return False
    return True


def _update(probe: Probe, args: argparse.Namespace) -> int:
    """Run `update`: each layer, a report of them on stdout, then the finish or how to do it."""
    run = UpdateRun(Path(args.project).resolve(), tuple(args.copier_args), finish=args.finish)
    layers = _layers_to_update(probe, run.project)
    if layers is None:
        return FAILED
    checks = update(probe, run, layers)
    sys.stdout.write(render(checks))
    if failed_checks(checks):
        return FAILED
    if _branch(probe, run.project) != UPDATE_BRANCH:
        logger.info("every layer is up to date; nothing to commit")
        return 0
    if run.finish:
        return 0 if finish_update(probe, run.project) else FAILED
    next_steps = UPDATE_NEXT_STEPS.format(
        branch=UPDATE_BRANCH, project=run.project, summary=UPDATE_SUMMARY
    )
    sys.stderr.write(next_steps)
    return 0


def failed_checks(checks: list[Check]) -> list[str]:
    """Return the names of the required checks that failed."""
    return [check.name for check in checks if check.required and not check.ok]


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
    new_parser = commands.add_parser(
        "new", help="generate a project from the CLI template, once doctor passes"
    )
    new_parser.add_argument("destination", help="the project's directory: new, or empty")
    new_parser.add_argument(
        "--template", default=CLI_TEMPLATE, help="the template to copy (default: %(default)s)"
    )
    new_parser.add_argument(
        "copier_args",
        nargs="*",
        metavar="-- COPIER_ARG",
        help="after --, passed to copier copy as is: -- --vcs-ref <commit>",
    )
    update_parser = commands.add_parser(
        "update", help="update a project from both its templates, committed on a branch"
    )
    update_parser.add_argument("project", help="the project's directory")
    update_parser.add_argument(
        "--finish", action="store_true", help="then merge the branch with tools/finish_branch.py"
    )
    update_parser.add_argument(
        "copier_args",
        nargs="*",
        metavar="-- COPIER_ARG",
        help="after --, passed to each copier update as is: -- --defaults",
    )
    pins_parser = commands.add_parser(
        "pins", help="show the uv pin beside uv's latest release, or move it with --update"
    )
    pins_parser.add_argument(
        "--update",
        choices=["uv"],
        help="move this pin everywhere it is written, on a branch here and in the CLI repo",
    )
    pins_parser.add_argument(
        "--to", metavar="VERSION", help="with --update, the version to move to (default: latest)"
    )
    pins_parser.add_argument(
        "--cli-repo",
        type=Path,
        help=f"with --update, the CLI template's clone (default: ../{CLI_REPO_NAME})",
    )
    return parser


def main(argv: list[str] | None = None, probe: Probe | None = None, root: Path = HERE) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    # force: basicConfig is a no-op once a handler exists, and a test calls main more than once.
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(levelname)s %(message)s", force=True
    )
    probe = probe or Probe()
    if args.command == "pins":
        return _pins(probe, root, args)
    if args.command == "update":
        return _update(probe, args)
    if args.command == "new":
        # Resolved now, so stdout names it absolutely: cd "$(sh bootstrap.sh new my-project)".
        destination = Path(args.destination).resolve()
        if not new(probe, destination, template=args.template, copier_args=args.copier_args):
            return FAILED
        sys.stdout.write(f"{destination}\n")
        return 0
    done = True
    if args.command == "setup":
        done = setup(probe, assume_yes=args.yes, noreply=args.noreply)
    # setup ends with doctor's report too, so a run shows what it left.
    checks = doctor(probe)
    sys.stdout.write(render(checks))
    failed = failed_checks(checks)
    if failed:
        logger.error("not ready: %s", ", ".join(failed))
    if failed or not done:
        return FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
