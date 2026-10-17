"""bootstrap.py, the helper: its pieces, then `doctor` end to end through `main`, on a fake machine.

The root is on pytest's `pythonpath`, so the helper is imported as a module and every probe of the
machine — commands, PATH lookups, the environment — is a `Probe` the test builds. Nothing here runs
a real command; tests/test_bootstrap_sh.py runs the helper for real, through the shim.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from bootstrap import Check, Probe, copier_settings_path, doctor, main, parse_tool_list, render

TOOL_LIST = """copier v9.18.2
- copier
prek v0.5.4
- prek
ruff v0.16.10
- ruff
"""
ON_PATH = {"uv", "git", "gh"}


@dataclass
class FakeMachine:
    """Answers commands from a table; a command missing from it fails, as an unknown one would."""

    answers: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    installed: set[str] = field(default_factory=ON_PATH.copy)

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        returncode, stdout = self.answers.get(tuple(command), (1, ""))
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def which(self, name: str) -> str | None:
        return f"/usr/bin/{name}" if name in self.installed else None


def _ready_machine() -> FakeMachine:
    return FakeMachine(
        answers={
            ("uv", "self", "version", "--short"): (0, "0.12.21\n"),
            ("uv", "tool", "list"): (0, TOOL_LIST),
            ("git", "config", "--get", "user.name"): (0, "A Dev\n"),
            ("git", "config", "--get", "user.email"): (0, "dev@example.com\n"),
            ("gh", "auth", "status"): (0, ""),
        }
    )


def _probe(machine: FakeMachine, home: Path) -> Probe:
    return Probe(run=machine.run, which=machine.which, env={}, home=home, system="Linux")


def _by_name(checks: list[Check]) -> dict[str, Check]:
    return {check.name: check for check in checks}


# --- the pieces ---------------------------------------------------------------------------


def test_parse_tool_list_reads_names_and_versions_and_skips_executables() -> None:
    assert parse_tool_list(TOOL_LIST) == {"copier": "9.18.2", "prek": "0.5.4", "ruff": "0.16.10"}


def test_parse_tool_list_of_nothing_is_empty() -> None:
    assert parse_tool_list("") == {}


@pytest.mark.parametrize(
    ("system", "env", "expected"),
    [
        ("Linux", {}, Path("/h/.config/copier/settings.yml")),
        ("Linux", {"XDG_CONFIG_HOME": "/xdg"}, Path("/xdg/copier/settings.yml")),
        ("Darwin", {}, Path("/h/Library/Application Support/copier/settings.yml")),
        ("Windows", {"LOCALAPPDATA": "/local"}, Path("/local/copier/settings.yml")),
        ("Linux", {"COPIER_SETTINGS_PATH": "/my/settings.yml"}, Path("/my/settings.yml")),
    ],
)
def test_copier_settings_path_follows_copier(
    system: str, env: dict[str, str], expected: Path
) -> None:
    assert copier_settings_path(env, Path("/h"), system) == expected


def test_render_aligns_names_and_marks_advice_as_warn() -> None:
    checks = [
        Check("uv", ok=True, detail="0.12.21"),
        Check("copier", ok=False, detail="missing"),
        Check("gh", ok=False, detail="not installed", required=False),
    ]
    assert render(checks) == (
        "ok   uv      0.12.21\nFAIL copier  missing\nwarn gh      not installed\n"
    )


# --- doctor -------------------------------------------------------------------------------


def test_doctor_on_a_ready_machine_passes_every_required_check(tmp_path: Path) -> None:
    checks = _by_name(doctor(_probe(_ready_machine(), tmp_path)))
    required = [check for check in checks.values() if check.required]
    assert all(check.ok for check in required), required
    assert checks["copier"].detail == "9.18.2"
    assert checks["git user.email"].detail == "dev@example.com"


def test_doctor_names_the_install_command_for_a_missing_tool(tmp_path: Path) -> None:
    machine = _ready_machine()
    machine.answers["uv", "tool", "list"] = (0, "prek v0.5.4\n- prek\n")
    copier = _by_name(doctor(_probe(machine, tmp_path)))["copier"]
    assert not copier.ok
    assert "uv tool install copier" in copier.detail


def test_doctor_without_uv_on_path_says_to_use_the_shim(tmp_path: Path) -> None:
    machine = _ready_machine()
    machine.installed.discard("uv")
    checks = _by_name(doctor(_probe(machine, tmp_path)))
    assert "bootstrap.sh" in checks["uv"].detail
    assert "copier" not in checks, "no uv, so no uv tools to list"


def test_doctor_fails_an_unset_git_email(tmp_path: Path) -> None:
    machine = _ready_machine()
    del machine.answers["git", "config", "--get", "user.email"]
    email = _by_name(doctor(_probe(machine, tmp_path)))["git user.email"]
    assert not email.ok
    assert "git config --global user.email" in email.detail


def test_doctor_finds_copier_settings_where_copier_reads_them(tmp_path: Path) -> None:
    settings = tmp_path / ".config" / "copier" / "settings.yml"
    settings.parent.mkdir(parents=True)
    settings.write_text("defaults: {}\n", encoding="utf-8")
    found = _by_name(doctor(_probe(_ready_machine(), tmp_path)))["copier settings"]
    assert found.ok
    assert found.detail == str(settings)


@pytest.mark.parametrize("logged_in", [True, False])
def test_doctor_treats_gh_as_advice(tmp_path: Path, logged_in: bool) -> None:
    machine = _ready_machine()
    if not logged_in:
        machine.answers["gh", "auth", "status"] = (1, "")
    gh = _by_name(doctor(_probe(machine, tmp_path)))["gh"]
    assert gh.ok is logged_in
    assert not gh.required


# --- through main -------------------------------------------------------------------------


def test_main_doctor_on_a_ready_machine_exits_0_with_the_report_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["doctor"], _probe(_ready_machine(), tmp_path)) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("ok   uv")
    assert captured.err == ""


def test_main_doctor_exits_1_and_names_what_failed_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    machine = _ready_machine()
    machine.answers["uv", "tool", "list"] = (0, "")
    assert main(["--yes", "doctor"], _probe(machine, tmp_path)) == 1
    captured = capsys.readouterr()
    assert "FAIL copier" in captured.out
    assert "copier, prek" in captured.err
