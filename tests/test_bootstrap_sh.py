"""bootstrap.sh, the shim: every branch against a stub uv, then once against the real installer.

Each case runs the real shim under /bin/sh with PATH holding only a stub `uv` and the few tools the
shim calls, so whatever uv the machine has never leaks in. The stub logs each call to a file and
answers from environment variables, which is how a case says what kind of uv it is. The module also
holds every copy of the uv pin to the shim's `UV_VERSION`.
"""

import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIM = REPO_ROOT / "bootstrap.sh"
HELPER = REPO_ROOT / "bootstrap.py"
PIN = re.search(r"^UV_VERSION=(\S+)$", SHIM.read_text(encoding="utf-8"), re.MULTILINE)
UV_VERSION = PIN.group(1) if PIN else ""

# What the shim and the stub installer run, linked into the stub PATH from wherever they really are.
SHIM_TOOLS = ("sh", "awk", "dirname", "mkdir", "cp")

STUB_UV = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
case "$*" in
    "self version --short")
        [ -n "$STUB_VERSION" ] || exit 2
        printf '%s\\n' "$STUB_VERSION" ;;
    "self update --dry-run") exit "$STUB_DRY_RUN_EXIT" ;;
    "self update "*) exit "$STUB_UPDATE_EXIT" ;;
    "run --script "*) exit "$STUB_RUN_EXIT" ;;
esac
"""

# Stands in for curl and wget: logs the URL, then serves an "installer" that puts the stub uv
# where the real installer puts uv.
STUB_FETCH = """#!/bin/sh
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$STUB_LOG"
printf 'mkdir -p "$HOME/.local/bin" && cp "$STUB_UV" "$HOME/.local/bin/uv"\\n'
"""

ON_CI = os.environ.get("CI") == "true"
posix_only = pytest.mark.skipif(os.name == "nt", reason="the shim is POSIX sh")


@dataclass(frozen=True)
class StubUv:
    """The uv a case runs against. `version=None` is a uv too old to have `self version`."""

    version: str | None = UV_VERSION
    dry_run_exit: int = 0
    update_exit: int = 0
    run_exit: int = 0
    on_path: bool = True


@dataclass(frozen=True)
class ShimRun:
    """What one run of the shim did: its exit code, its stderr, and every call the stub saw."""

    returncode: int
    stderr: str
    calls: list[str]


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _stub_bin(tmp_path: Path, uv: StubUv, fetcher: str) -> Path:
    """Return a PATH directory with the shim's tools, a fetcher, and the stub uv if it is on PATH."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _write_executable(stubs / "uv", STUB_UV)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in (*SHIM_TOOLS, "basename"):
        real = shutil.which(tool)
        assert real is not None, f"{tool} is not on PATH"
        (bin_dir / tool).symlink_to(real)
    _write_executable(bin_dir / fetcher, STUB_FETCH)
    if uv.on_path:
        (bin_dir / "uv").symlink_to(stubs / "uv")
    return bin_dir


def _run_shim(tmp_path: Path, uv: StubUv, *args: str, fetcher: str = "curl") -> ShimRun:
    """Run the shim with `args` against `uv`, with no terminal on stdin."""
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        "PATH": str(_stub_bin(tmp_path, uv, fetcher)),
        "HOME": str(tmp_path / "home"),
        "STUB_LOG": str(log),
        "STUB_UV": str(tmp_path / "stubs" / "uv"),
        "STUB_VERSION": uv.version or "",
        "STUB_DRY_RUN_EXIT": str(uv.dry_run_exit),
        "STUB_UPDATE_EXIT": str(uv.update_exit),
        "STUB_RUN_EXIT": str(uv.run_exit),
    }
    completed = subprocess.run(
        ["/bin/sh", str(SHIM), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines()
    return ShimRun(completed.returncode, completed.stderr, calls)


def _handoff(*args: str) -> str:
    """The call that hands off to bootstrap.py, as the stub logs it."""
    return " ".join(["run", "--script", str(HELPER), *args])


# --- a uv it can trust --------------------------------------------------------------------


@posix_only
@pytest.mark.parametrize("version", [UV_VERSION, "0.12.22", "0.13.0", "1.0.0"])
def test_a_standalone_uv_at_or_above_the_pin_hands_off(tmp_path: Path, version: str) -> None:
    run = _run_shim(tmp_path, StubUv(version=version), "doctor")
    assert run.returncode == 0, run.stderr
    assert run.calls == ["self version --short", "self update --dry-run", _handoff("doctor")]


@posix_only
def test_the_helper_exit_code_is_the_shims(tmp_path: Path) -> None:
    run = _run_shim(tmp_path, StubUv(run_exit=3), "doctor")
    assert run.returncode == 3


# --- no uv --------------------------------------------------------------------------------


@posix_only
def test_no_uv_and_no_terminal_refuses_without_yes(tmp_path: Path) -> None:
    run = _run_shim(tmp_path, StubUv(on_path=False), "doctor")
    assert run.returncode == 1
    assert "--yes" in run.stderr
    assert run.calls == [], "nothing may be downloaded without consent"


@posix_only
@pytest.mark.parametrize("fetcher", ["curl", "wget"])
def test_no_uv_with_yes_installs_the_pin_and_uses_it(tmp_path: Path, fetcher: str) -> None:
    run = _run_shim(tmp_path, StubUv(on_path=False), "--yes", "doctor", fetcher=fetcher)
    assert run.returncode == 0, run.stderr
    assert run.calls[0].startswith(fetcher)
    assert f"https://astral.sh/uv/{UV_VERSION}/install.sh" in run.calls[0]
    assert run.calls[1:] == [
        "self version --short",
        "self update --dry-run",
        _handoff("--yes", "doctor"),
    ]


# --- a uv it cannot trust -----------------------------------------------------------------


@posix_only
def test_a_uv_that_cannot_update_itself_stops(tmp_path: Path) -> None:
    run = _run_shim(tmp_path, StubUv(dry_run_exit=2), "doctor")
    assert run.returncode == 1
    assert "cannot update itself" in run.stderr
    assert _handoff("doctor") not in run.calls


@posix_only
@pytest.mark.parametrize("version", ["0.12.3", "0.9.0", None])
def test_a_uv_below_the_pin_is_not_updated_without_consent(
    tmp_path: Path, version: str | None
) -> None:
    """0.12.3 and 0.9.0 sort above the pin as strings: the comparison must be numeric."""
    run = _run_shim(tmp_path, StubUv(version=version), "doctor")
    assert run.returncode == 1
    assert "older than" in run.stderr
    assert "--yes" in run.stderr
    assert run.calls == ["self version --short"]


@posix_only
def test_a_uv_below_the_pin_is_updated_to_it_with_yes(tmp_path: Path) -> None:
    run = _run_shim(tmp_path, StubUv(version="0.12.3"), "--yes", "doctor")
    assert run.returncode == 0, run.stderr
    assert run.calls == [
        "self version --short",
        f"self update {UV_VERSION}",
        _handoff("--yes", "doctor"),
    ]


@posix_only
def test_a_uv_below_the_pin_that_cannot_update_itself_stops(tmp_path: Path) -> None:
    run = _run_shim(tmp_path, StubUv(version="0.12.3", update_exit=2), "--yes", "doctor")
    assert run.returncode == 1
    assert "cannot update itself" in run.stderr
    assert _handoff("--yes", "doctor") not in run.calls


# --- the real thing -----------------------------------------------------------------------


@posix_only
@pytest.mark.skipif(not ON_CI, reason="downloads uv and a Python; CI only")
def test_the_shim_installs_the_real_uv_on_a_bare_machine(tmp_path: Path) -> None:
    """A HOME with nothing in it and a PATH with no uv: the official installer, at the pin, then
    doctor, which must find that uv although PATH never named it. Nothing else is installed, so
    doctor reports the machine not ready.
    """
    bare_path = "/usr/bin:/bin"
    assert shutil.which("uv", path=bare_path) is None, "this runner has a uv outside the tool cache"
    env = {"HOME": str(tmp_path), "PATH": bare_path}
    completed = subprocess.run(
        ["/bin/sh", str(SHIM), "--yes", "doctor"],
        cwd=tmp_path,  # away from the repo's .venv, so uv fetches a Python as on a bare machine
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    report = completed.stdout.splitlines()
    assert completed.returncode == 1, completed.stderr
    assert report[0].split() == ["ok", "uv", UV_VERSION], completed.stdout
    assert report[1].split()[:2] == ["FAIL", "copier"], completed.stdout


# --- the pin ------------------------------------------------------------------------------


def test_every_copy_of_the_uv_pin_agrees() -> None:
    """The shim's UV_VERSION is the pin; each other copy is a floor of it or CI's exact version."""
    assert UV_VERSION, "bootstrap.sh has no UV_VERSION= line"
    floor = f">={UV_VERSION}"
    root = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["uv"]["required-version"] == floor
    template = (REPO_ROOT / "template" / "pyproject.toml.jinja").read_text(encoding="utf-8")
    assert re.findall(r'^required-version = "(.*)"$', template, re.MULTILINE) == [floor]
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    setups = ci.count("uses: astral-sh/setup-uv@")
    versions = re.findall(r'^\s+version: "(.*)"$', ci, re.MULTILINE)
    assert versions == [UV_VERSION] * setups, "each setup-uv step must run the floor"
