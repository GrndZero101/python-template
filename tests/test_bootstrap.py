"""bootstrap.py, the helper: its pieces, then each command end to end through `main`, on a fake machine.

The root is on pytest's `pythonpath`, so the helper is imported as a module and every probe of the
machine — commands, PATH lookups, the environment — is a `Probe` the test builds. Nothing here runs
a real command; tests/test_bootstrap_sh.py runs the helper for real, through the shim.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from bootstrap import (
    Check,
    Probe,
    choose_email,
    copier_settings_path,
    doctor,
    main,
    noreply_email,
    parse_tool_list,
    render,
    settings_text,
    setup,
    upgrade_uv_tools,
    write_settings,
)

TOOL_LIST = """copier v9.18.2
- copier
prek v0.5.4
- prek
ruff v0.16.10
- ruff
"""
ON_PATH = {"uv", "git", "gh"}
GH_USER = '{"id": 123, "login": "adev", "email": null}'
NOREPLY = "123+adev@users.noreply.github.com"


@dataclass
class FakeMachine:
    """Answers commands from a table; a command missing from it fails, as an unknown one would.

    Questions get `agree` for an answer, and both they and the commands are kept, in order.
    """

    answers: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    installed: set[str] = field(default_factory=ON_PATH.copy)
    agree: bool = False
    ran: list[tuple[str, ...]] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.ran.append(tuple(command))
        returncode, stdout = self.answers.get(tuple(command), (1, ""))
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def confirm(self, question: str) -> bool:
        self.asked.append(question)
        return self.agree

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
            ("gh", "api", "user"): (0, GH_USER),
            ("uv", "tool", "upgrade", "copier"): (0, ""),
            ("uv", "tool", "upgrade", "prek"): (0, ""),
        }
    )


def _probe(machine: FakeMachine, home: Path, *, interactive: bool = False) -> Probe:
    return Probe(
        run=machine.run,
        which=machine.which,
        env={},
        home=home,
        system="Linux",
        confirm=machine.confirm,
        interactive=interactive,
    )


def _settings(home: Path) -> Path:
    return home / ".config" / "copier" / "settings.yml"


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
    settings = _settings(tmp_path)
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


# --- setup -------------------------------------------------------------------------------


def test_upgrade_uv_tools_installs_what_is_missing_and_upgrades_the_rest(tmp_path: Path) -> None:
    machine = _ready_machine()
    machine.answers["uv", "tool", "list"] = (0, "copier v9.18.2\n- copier\n")
    machine.answers["uv", "tool", "install", "prek"] = (0, "")
    assert upgrade_uv_tools(_probe(machine, tmp_path))
    assert ("uv", "tool", "upgrade", "copier") in machine.ran
    assert ("uv", "tool", "install", "prek") in machine.ran


def test_upgrade_uv_tools_reports_a_failed_install(tmp_path: Path) -> None:
    machine = _ready_machine()
    del machine.answers["uv", "tool", "upgrade", "prek"]
    assert not upgrade_uv_tools(_probe(machine, tmp_path))


def test_noreply_email_is_built_from_the_gh_users_id_and_login(tmp_path: Path) -> None:
    assert noreply_email(_probe(_ready_machine(), tmp_path)) == NOREPLY


def test_noreply_email_needs_gh_logged_in(tmp_path: Path) -> None:
    machine = _ready_machine()
    machine.answers["gh", "api", "user"] = (1, "")
    assert noreply_email(_probe(machine, tmp_path)) is None


@pytest.mark.parametrize(
    ("noreply", "interactive", "agree", "expected"),
    [
        (True, False, False, NOREPLY),
        (False, True, True, NOREPLY),
        (False, True, False, "dev@example.com"),
        (False, False, False, "dev@example.com"),
    ],
)
def test_choose_email_offers_the_noreply_address(
    tmp_path: Path, *, noreply: bool, interactive: bool, agree: bool, expected: str
) -> None:
    machine = _ready_machine()
    machine.agree = agree
    probe = _probe(machine, tmp_path, interactive=interactive)
    assert choose_email(probe, "dev@example.com", noreply=noreply) == expected


def test_choose_email_asks_nothing_when_git_already_uses_the_noreply_address(
    tmp_path: Path,
) -> None:
    machine = _ready_machine()
    probe = _probe(machine, tmp_path, interactive=True)
    assert choose_email(probe, NOREPLY, noreply=False) == NOREPLY
    assert machine.asked == []


def test_settings_text_is_yaml_that_copier_reads_back() -> None:
    text = settings_text('A "Quoted" Dév', "")
    assert yaml.safe_load(text) == {
        "defaults": {"author_name": 'A "Quoted" Dév', "author_email": ""}
    }


def test_write_settings_creates_a_missing_file_without_asking(tmp_path: Path) -> None:
    machine = _ready_machine()
    path = _settings(tmp_path)
    assert write_settings(_probe(machine, tmp_path), path, "new\n", assume_yes=False)
    assert path.read_text(encoding="utf-8") == "new\n"
    assert machine.asked == []


def test_write_settings_leaves_an_identical_file_alone(tmp_path: Path) -> None:
    machine = _ready_machine()
    path = _settings(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("same\n", encoding="utf-8")
    assert write_settings(
        _probe(machine, tmp_path, interactive=True), path, "same\n", assume_yes=False
    )
    assert machine.asked == []


@pytest.mark.parametrize(
    ("interactive", "agree", "assume_yes", "succeeds", "replaced"),
    [
        (False, False, False, False, False),  # no way to ask: refuse, naming --yes
        (False, False, True, True, True),
        (True, True, False, True, True),
        (True, False, False, True, False),  # a "no" is an answer, not a failure
    ],
)
def test_write_settings_shows_the_diff_and_asks_before_replacing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    interactive: bool,
    agree: bool,
    assume_yes: bool,
    succeeds: bool,
    replaced: bool,
) -> None:
    machine = _ready_machine()
    machine.agree = agree
    path = _settings(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("old\n", encoding="utf-8")
    probe = _probe(machine, tmp_path, interactive=interactive)
    assert write_settings(probe, path, "new\n", assume_yes=assume_yes) is succeeds
    assert path.read_text(encoding="utf-8") == ("new\n" if replaced else "old\n")
    captured = capsys.readouterr()
    assert "-old\n+new\n" in captured.err
    assert captured.out == ""


def test_setup_without_a_git_name_writes_no_settings(tmp_path: Path) -> None:
    machine = _ready_machine()
    del machine.answers["git", "config", "--get", "user.name"]
    assert not setup(_probe(machine, tmp_path), assume_yes=False, noreply=False)
    assert not _settings(tmp_path).exists()


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


def test_main_setup_writes_settings_from_git_and_ends_with_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    machine = _ready_machine()
    assert main(["setup"], _probe(machine, tmp_path)) == 0
    settings = yaml.safe_load(_settings(tmp_path).read_text(encoding="utf-8"))
    assert settings == {"defaults": {"author_name": "A Dev", "author_email": "dev@example.com"}}
    assert ("uv", "tool", "upgrade", "copier") in machine.ran
    assert capsys.readouterr().out.startswith("ok   uv")


def test_main_setup_noreply_answers_with_the_github_address(tmp_path: Path) -> None:
    assert main(["setup", "--noreply"], _probe(_ready_machine(), tmp_path)) == 0
    settings = yaml.safe_load(_settings(tmp_path).read_text(encoding="utf-8"))
    assert settings["defaults"]["author_email"] == NOREPLY


def test_main_setup_exits_1_when_a_tool_fails_even_if_doctor_passes(tmp_path: Path) -> None:
    machine = _ready_machine()
    del machine.answers["uv", "tool", "upgrade", "prek"]
    assert main(["setup"], _probe(machine, tmp_path)) == 1
