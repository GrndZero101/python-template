"""bootstrap.py, the helper: its pieces, then each command end to end through `main`, on a fake machine.

The root is on pytest's `pythonpath`, so the helper is imported as a module and every probe of the
machine — commands, PATH lookups, the environment — is a `Probe` the test builds. Nothing here runs
a real command; tests/test_bootstrap_sh.py runs the helper for real, through the shim.
"""

import dataclasses
import functools
import json
import shutil
import subprocess
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from bootstrap import (
    BASE_UV_SITES,
    CLI_REPO_NAME,
    CLI_TEMPLATE,
    CLI_UV_SITES,
    PIN_COMMIT_BODY,
    UPDATE_BRANCH,
    UPDATE_SUMMARY,
    UV_RELEASES,
    Check,
    Layer,
    PinSite,
    Probe,
    UpdateRun,
    choose_email,
    copier_settings_path,
    doctor,
    main,
    move_uv,
    new,
    noreply_email,
    parse_tool_list,
    pin_checks,
    read_layer,
    read_pin,
    render,
    resolve_target,
    rewrite_pin,
    settings_text,
    setup,
    upgrade_uv_tools,
    version_key,
    write_settings,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN = read_pin(REPO_ROOT)
NEWER = "99.1.2"

TOOL_LIST = """copier v9.18.2
- copier
prek v0.5.4
- prek
ruff v0.16.10
- ruff
"""
ON_PATH = {"uv", "git", "gh", "copier"}
GH_USER = '{"id": 123, "login": "adev", "email": null}'
NOREPLY = "123+adev@users.noreply.github.com"


@dataclass
class FakeMachine:
    """Answers commands from a table; a command missing from it fails, as an unknown one would.

    A command in `queued` takes its answers from there in turn, until they run out. One in
    `effects` does that to the files too, as copier would. `git branch --show-current` answers
    with `branch`, which a `git switch --create` that succeeds moves.

    Questions get `agree` for an answer, and both they and the commands are kept, in order. PyPI
    answers with `latest` for uv's newest release, or cannot be reached when it is None.
    """

    answers: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    queued: dict[tuple[str, ...], list[tuple[int, str]]] = field(default_factory=dict)
    effects: dict[tuple[str, ...], Callable[[], None]] = field(default_factory=dict)
    branch: str = "main"
    installed: set[str] = field(default_factory=ON_PATH.copy)
    agree: bool = False
    latest: str | None = PIN
    ran: list[tuple[str, ...]] = field(default_factory=list)
    envs: dict[tuple[str, ...], Mapping[str, str] | None] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def _answer(self, command: list[str], env: Mapping[str, str] | None) -> tuple[int, str]:
        key = tuple(command)
        self.ran.append(key)
        self.envs[key] = env
        effect = self.effects.get(key)
        if effect is not None:
            effect()
        if command[3:] == ["branch", "--show-current"]:
            return 0, f"{self.branch}\n"
        queue = self.queued.get(key)
        answer = queue.pop(0) if queue else self.answers.get(key, (1, ""))
        if command[3:5] == ["switch", "--create"] and answer[0] == 0:
            self.branch = command[5]
        return answer

    def run(
        self, command: list[str], env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        returncode, stdout = self._answer(command, env)
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def fetch(self, url: str) -> bytes:
        assert url == UV_RELEASES
        if self.latest is None:
            raise urllib.error.URLError(url)
        return json.dumps({"info": {"version": self.latest}}).encode()

    def attach(self, command: list[str], env: Mapping[str, str] | None = None) -> int:
        return self._answer(command, env)[0]

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
        attach=machine.attach,
        which=machine.which,
        env={},
        home=home,
        system="Linux",
        confirm=machine.confirm,
        interactive=interactive,
        fetch=machine.fetch,
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


# --- new ---------------------------------------------------------------------------------


def _copy(destination: Path, *copier_args: str) -> tuple[str, ...]:
    return ("copier", "copy", "--trust", *copier_args, CLI_TEMPLATE, str(destination))


def test_new_copies_the_cli_template_into_a_new_directory(tmp_path: Path) -> None:
    machine = _ready_machine()
    destination = tmp_path / "my-project"
    machine.answers[_copy(destination)] = (0, "")
    assert new(_probe(machine, tmp_path), destination, template=CLI_TEMPLATE, copier_args=[])
    assert machine.ran[-1] == _copy(destination)


def test_new_accepts_an_existing_empty_directory(tmp_path: Path) -> None:
    machine = _ready_machine()
    machine.answers[_copy(tmp_path)] = (0, "")
    assert new(_probe(machine, tmp_path), tmp_path, template=CLI_TEMPLATE, copier_args=[])


@pytest.mark.parametrize("occupant", ["a file", "a directory with a file in it"])
def test_new_refuses_a_destination_with_something_there(tmp_path: Path, occupant: str) -> None:
    machine = _ready_machine()
    destination = tmp_path / "my-project"
    if occupant == "a file":
        destination.write_text("", encoding="utf-8")
    else:
        destination.mkdir()
        (destination / "README.md").write_text("", encoding="utf-8")
    assert not new(_probe(machine, tmp_path), destination, template=CLI_TEMPLATE, copier_args=[])
    assert machine.ran[-1][0] != "copier"


def test_new_needs_copier_on_path(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    machine = _ready_machine()
    machine.installed.discard("copier")
    assert not new(_probe(machine, tmp_path), tmp_path / "p", template=CLI_TEMPLATE, copier_args=[])
    assert "uv tool update-shell" in caplog.text


def test_new_reports_copiers_failure(tmp_path: Path) -> None:
    machine = _ready_machine()
    destination = tmp_path / "my-project"
    machine.answers[_copy(destination)] = (4, "")
    assert not new(_probe(machine, tmp_path), destination, template=CLI_TEMPLATE, copier_args=[])


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


def test_main_new_writes_the_projects_path_and_nothing_else_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    machine = _ready_machine()
    destination = tmp_path / "my-project"
    machine.answers[_copy(destination, "--defaults", "--vcs-ref", "abc123")] = (0, "")
    monkeypatch.chdir(tmp_path)
    argv = ["new", "my-project", "--", "--defaults", "--vcs-ref", "abc123"]
    assert main(argv, _probe(machine, tmp_path)) == 0
    assert capsys.readouterr().out == f"{destination}\n"


def test_main_new_on_a_machine_doctor_fails_runs_no_copier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    machine = _ready_machine()
    machine.answers["uv", "tool", "list"] = (0, "")
    assert main(["new", str(tmp_path / "p")], _probe(machine, tmp_path)) == 1
    assert not any(command[0] == "copier" for command in machine.ran)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FAIL copier" in captured.err
    assert "bootstrap.sh setup" in captured.err


# --- pins ---------------------------------------------------------------------------------


def _repos(tmp_path: Path) -> tuple[Path, Path]:
    """Return a base and a CLI repo holding real copies of every file the uv pin is written in.

    The CLI repo's files are the base's, which write the pin the same way.
    """
    base = tmp_path / "base"
    cli = tmp_path / CLI_REPO_NAME
    for root, sites in ((base, BASE_UV_SITES), (cli, CLI_UV_SITES)):
        for site in sites:
            destination = root / site.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / site.path, destination)
    return base, cli


def _git(root: Path, *args: str) -> tuple[str, ...]:
    return ("git", "-C", str(root), *args)


def _commit(root: Path, version: str) -> tuple[str, ...]:
    message = f"build(uv): raise the uv floor to {version}"
    return _git(root, "commit", "-m", message, "-m", PIN_COMMIT_BODY)


def _movable(base: Path, cli: Path | None = None, version: str = NEWER) -> FakeMachine:
    """A machine on which each repo is clean, and switching, staging and committing there work."""
    machine = FakeMachine(latest=version)
    machine.answers["uv", "self", "version", "--short"] = (0, f"{version}\n")
    repos = [(base, BASE_UV_SITES)]
    if cli is not None:
        repos.append((cli, CLI_UV_SITES))
    for root, sites in repos:
        machine.answers[_git(root, "status", "--porcelain")] = (0, "")
        machine.answers[_git(root, "switch", "--create", f"build/uv-{version}", "main")] = (0, "")
        paths = [str(Path(site.path)) for site in sites]
        machine.answers[_git(root, "add", "--", *paths)] = (0, "")
        machine.answers[_commit(root, version)] = (0, "")
    return machine


def _contents(*roots: Path) -> dict[Path, str]:
    contents: dict[Path, str] = {}
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                contents[path] = path.read_text(encoding="utf-8")
    return contents


def _pins_found(root: Path, sites: tuple[PinSite, ...]) -> set[str]:
    found: set[str] = set()
    for site in sites:
        text = (root / site.path).read_text(encoding="utf-8")
        found.update(match["version"] for match in site.pattern.finditer(text))
    return found


def test_version_key_compares_numerically() -> None:
    assert version_key("0.13.0") > version_key("0.9.10")


def test_rewrite_pin_moves_every_copy_in_a_file() -> None:
    text = 'a\n  version: "1.0.0"\nb\n  version: "1.0.0"\n'
    moved = rewrite_pin(text, CLI_UV_SITES[2], "1.0.0", "2.0.0")
    assert moved == 'a\n  version: "2.0.0"\nb\n  version: "2.0.0"\n'


@pytest.mark.parametrize("text", ["UV_VERSION=1.0.1\n", "no pin here\n"])
def test_rewrite_pin_refuses_a_file_not_holding_the_pin(text: str) -> None:
    assert rewrite_pin(text, BASE_UV_SITES[0], "1.0.0", "2.0.0") is None


def test_rewrite_pin_keeps_crlf_line_endings() -> None:
    moved = rewrite_pin("UV_VERSION=1.0.0\r\n", BASE_UV_SITES[0], "1.0.0", "2.0.0")
    assert moved == "UV_VERSION=2.0.0\r\n"


@pytest.mark.parametrize(
    ("rev", "expected"), [("1.0.0", "2.0.0"), ("1.5.0", "2.0.0"), ("2.1.0", "2.1.0")]
)
def test_rewrite_pin_raises_an_at_least_site_only_below_the_new_pin(
    rev: str, expected: str
) -> None:
    hook = "  - repo: https://github.com/astral-sh/uv-pre-commit\n    rev: {}\n    hooks:\n"
    moved = rewrite_pin(hook.format(rev), BASE_UV_SITES[-1], "1.0.0", "2.0.0")
    assert moved == hook.format(expected)


@pytest.mark.parametrize(
    ("latest", "ok", "detail"),
    [
        (PIN, True, f"{PIN}, the latest"),
        (NEWER, False, f"{PIN}, latest {NEWER}: sh bootstrap.sh pins --update uv"),
        (None, False, f"{PIN}, latest unknown"),
    ],
)
def test_pin_checks_show_the_pin_beside_the_latest_release(
    tmp_path: Path, latest: str | None, ok: bool, detail: str
) -> None:
    checks = pin_checks(_probe(FakeMachine(latest=latest), tmp_path), REPO_ROOT)
    assert checks == [Check("uv", ok=ok, detail=detail, required=ok)]


@pytest.mark.parametrize(
    ("requested", "latest", "expected"),
    [
        (None, NEWER, NEWER),
        ("99.0.0", NEWER, "99.0.0"),
        (PIN, NEWER, PIN),
        ("0.1.0", NEWER, None),
        ("latest", NEWER, None),
        (None, None, None),
    ],
)
def test_resolve_target_takes_the_latest_or_a_higher_version(
    tmp_path: Path, requested: str | None, latest: str | None, expected: str | None
) -> None:
    probe = _probe(FakeMachine(latest=latest), tmp_path)
    assert resolve_target(probe, PIN, requested) == expected


def test_move_uv_moves_every_copy_and_commits_on_a_branch_in_each_repo(tmp_path: Path) -> None:
    base, cli = _repos(tmp_path)
    machine = _movable(base, cli)
    assert move_uv(_probe(machine, tmp_path), base, cli, NEWER)
    assert _pins_found(base, BASE_UV_SITES) == {NEWER}
    assert _pins_found(cli, CLI_UV_SITES) == {NEWER}
    for root in (base, cli):
        env = machine.envs[_commit(root, NEWER)]
        assert env is not None
        assert env["SKIP"] == "generation-tests"


def test_move_uv_changes_nothing_while_either_repo_is_dirty(tmp_path: Path) -> None:
    base, cli = _repos(tmp_path)
    machine = _movable(base, cli)
    machine.answers[_git(cli, "status", "--porcelain")] = (0, " M README.md\n")
    before = _contents(base, cli)
    assert not move_uv(_probe(machine, tmp_path), base, cli, NEWER)
    assert _contents(base, cli) == before
    assert not any("switch" in command for command in machine.ran)


def test_move_uv_changes_nothing_when_a_copy_disagrees(tmp_path: Path) -> None:
    base, cli = _repos(tmp_path)
    ci = cli / CLI_UV_SITES[2].path
    ci.write_text(ci.read_text(encoding="utf-8").replace(PIN, "0.1.0", 1), encoding="utf-8")
    machine = _movable(base, cli)
    before = _contents(base, cli)
    assert not move_uv(_probe(machine, tmp_path), base, cli, NEWER)
    assert _contents(base, cli) == before
    assert not any("switch" in command for command in machine.ran)


def test_main_pins_reports_on_stdout_and_exits_0_even_when_behind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["pins"], _probe(FakeMachine(latest=NEWER), tmp_path), REPO_ROOT) == 0
    assert capsys.readouterr().out.startswith(f"warn uv  {PIN}, latest {NEWER}")


def test_main_pins_update_finds_the_cli_repo_beside_this_one(tmp_path: Path) -> None:
    base, cli = _repos(tmp_path)
    machine = _movable(base, cli)
    assert main(["pins", "--update", "uv"], _probe(machine, tmp_path), base) == 0
    assert _pins_found(cli, CLI_UV_SITES) == {NEWER}


def test_main_pins_update_refuses_a_floor_above_the_running_uv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cli = _repos(tmp_path)
    machine = _movable(base, cli)
    machine.answers["uv", "self", "version", "--short"] = (0, f"{PIN}\n")
    before = _contents(base, cli)
    assert main(["pins", "--update", "uv"], _probe(machine, tmp_path), base) == 1
    assert f"uv self update {NEWER}" in capsys.readouterr().err
    assert _contents(base, cli) == before
    assert not any(command[0] == "git" for command in machine.ran)


def test_main_pins_update_needs_the_cli_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cli = _repos(tmp_path)
    shutil.rmtree(cli)
    assert main(["pins", "--update", "uv"], _probe(_movable(base), tmp_path), base) == 1
    assert "--cli-repo" in capsys.readouterr().err


def test_main_pins_update_to_the_pin_is_nothing_to_do(tmp_path: Path) -> None:
    base, _ = _repos(tmp_path)
    machine = FakeMachine()
    assert main(["pins", "--update", "uv", "--to", PIN], _probe(machine, tmp_path), base) == 0
    assert machine.ran == []


# --- update -------------------------------------------------------------------------------

USE_CASE = (".copier-answers.yml", "gh:GrndZero101/python-template-cli-typer", "aaa1111")
BASE = (".copier-answers.base.yml", "gh:GrndZero101/python-template-base", "bbb2222")
MOVED_TO = "ccc3333"
CHANGED = (0, " M CLAUDE.md\n")
UNCHANGED = (0, "")


def _write_answers(project: Path, answers: str, source: str, commit: str) -> None:
    text = f"# Changes here will be overwritten by Copier\n_commit: {commit}\n_src_path: {source}\n"
    (project / answers).write_text(text, encoding="utf-8")


def _project(tmp_path: Path, *layers: tuple[str, str, str]) -> Path:
    """Return a project directory holding an answers file for each of `layers`."""
    project = tmp_path / "my-project"
    project.mkdir()
    for answers, source, commit in layers:
        _write_answers(project, answers, source, commit)
    return project


def _copier_update(project: Path, answers: str, *copier_args: str) -> tuple[str, ...]:
    return ("copier", "update", "--trust", "-a", answers, *copier_args, str(project))


def _updatable(
    project: Path,
    *layers: tuple[str, str, str],
    after: list[tuple[int, str]],
    copier_args: tuple[str, ...] = (),
) -> FakeMachine:
    """A ready machine on which `project` is clean on main and copier moves each layer.

    `after` is what `git status --porcelain` says after each layer's update, in turn.
    """
    machine = _ready_machine()
    status = _git(project, "status", "--porcelain")
    machine.queued[status] = [UNCHANGED, *after]
    for answers, source, _ in layers:
        command = _copier_update(project, answers, *copier_args)
        machine.answers[command] = (0, "")
        machine.effects[command] = functools.partial(
            _write_answers, project, answers, source, MOVED_TO
        )
        message = f"chore(template): update {Layer(answers, source, '').name} to {MOVED_TO}"
        machine.answers[_git(project, "commit", "-m", message)] = (0, "")
    machine.answers[_git(project, "diff", "--name-only", "--diff-filter=U")] = (0, "")
    machine.answers["uv", "sync", "--directory", str(project)] = (0, "")
    machine.answers[_git(project, "switch", "--create", UPDATE_BRANCH)] = (0, "")
    machine.answers[_git(project, "add", "--all")] = (0, "")
    return machine


def _commits(machine: FakeMachine) -> list[str]:
    return [command[-1] for command in machine.ran if command[3:5] == ("commit", "-m")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "_commit: aaa1111\n_src_path: gh:GrndZero101/python-template-cli-typer\n",
            Layer(".copier-answers.yml", "gh:GrndZero101/python-template-cli-typer", "aaa1111"),
        ),
        (
            "_commit: '1234567'\r\n_src_path: /templates/python-template-base/\r\n",
            Layer(".copier-answers.yml", "/templates/python-template-base/", "1234567"),
        ),
    ],
)
def test_read_layer_reads_the_commit_and_source(tmp_path: Path, text: str, expected: Layer) -> None:
    (tmp_path / ".copier-answers.yml").write_text(text, encoding="utf-8", newline="")
    assert read_layer(tmp_path, ".copier-answers.yml") == expected


def test_read_layer_of_a_missing_file_is_none(tmp_path: Path) -> None:
    assert read_layer(tmp_path, ".copier-answers.base.yml") is None


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("gh:GrndZero101/python-template-base", "python-template-base"),
        ("https://github.com/GrndZero101/python-template-base.git", "python-template-base"),
        ("C:\\templates\\python-template-base\\", "python-template-base"),
        ("", ".copier-answers.yml"),
    ],
)
def test_a_layer_is_named_for_its_repository(source: str, name: str) -> None:
    assert Layer(".copier-answers.yml", source, "aaa1111").name == name


def test_a_rerun_repeats_what_was_asked() -> None:
    run = UpdateRun(Path("/p"), ("--defaults", "--data", "a=b c"), finish=True)
    assert run.rerun().endswith(f"update {Path('/p')} --finish -- --defaults --data 'a=b c'")


def test_main_update_commits_each_layer_on_a_branch_and_reports_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, USE_CASE, BASE)
    machine = _updatable(project, USE_CASE, BASE, after=[CHANGED, CHANGED])
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 0
    assert machine.branch == UPDATE_BRANCH
    assert _commits(machine) == [
        f"chore(template): update python-template-cli-typer to {MOVED_TO}",
        f"chore(template): update python-template-base to {MOVED_TO}",
    ]
    captured = capsys.readouterr()
    assert captured.out == (
        f"ok   python-template-cli-typer  aaa1111 -> {MOVED_TO}\n"
        f"ok   python-template-base       bbb2222 -> {MOVED_TO}\n"
    )
    assert "tools/finish_branch.py" in captured.err


def test_main_update_runs_the_use_case_first_then_the_base(tmp_path: Path) -> None:
    project = _project(tmp_path, USE_CASE, BASE)
    machine = _updatable(project, USE_CASE, BASE, after=[CHANGED, CHANGED])
    main(["update", str(project)], _probe(machine, tmp_path))
    copier = [command[4] for command in machine.ran if command[0] == "copier"]
    assert copier == [".copier-answers.yml", ".copier-answers.base.yml"]


def test_main_update_with_nothing_new_makes_no_branch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, USE_CASE, BASE)
    machine = _updatable(project, USE_CASE, BASE, after=[UNCHANGED, UNCHANGED])
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 0
    assert machine.branch == "main"
    assert _commits(machine) == []
    assert "ok   python-template-base       already at bbb2222" in capsys.readouterr().out


def test_main_update_of_a_project_from_the_base_alone_updates_the_base(tmp_path: Path) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 0
    assert _commits(machine) == [f"chore(template): update python-template-base to {MOVED_TO}"]


def test_main_update_passes_what_follows_the_dashes_to_each_copier_update(tmp_path: Path) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED], copier_args=("--defaults",))
    assert main(["update", str(project), "--", "--defaults"], _probe(machine, tmp_path)) == 0
    assert _copier_update(project, BASE[0], "--defaults") in machine.ran


def test_main_update_stops_at_a_conflict_on_the_branch_and_says_how_to_carry_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, USE_CASE, BASE)
    machine = _updatable(
        project, USE_CASE, BASE, after=[CHANGED, CHANGED], copier_args=("--defaults",)
    )
    machine.answers[_git(project, "diff", "--name-only", "--diff-filter=U")] = (0, "README.md\n")
    assert main(["update", str(project), "--", "--defaults"], _probe(machine, tmp_path)) == 1
    assert machine.branch == UPDATE_BRANCH, "the commit that resolves it must land off main"
    assert _commits(machine) == []
    assert not any(command[4:5] == (BASE[0],) for command in machine.ran), "the base is next"
    captured = capsys.readouterr()
    assert captured.out == "FAIL python-template-cli-typer  conflicts in README.md\n"
    assert f'git commit -m "chore(template): update python-template-cli-typer to {MOVED_TO}"' in (
        captured.err
    )
    assert f"update {project} -- --defaults" in captured.err


def test_main_update_stops_when_uv_sync_fails(tmp_path: Path) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    del machine.answers["uv", "sync", "--directory", str(project)]
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 1
    assert _commits(machine) == []


def test_main_update_reports_a_commit_its_hooks_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    message = f"chore(template): update python-template-base to {MOVED_TO}"
    machine.answers[_git(project, "commit", "-m", message)] = (1, "ruff check....Failed")
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("FAIL python-template-base")
    assert "ruff check....Failed" in captured.err


def test_main_update_runs_uv_in_the_project_without_the_helpers_virtual_env(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    probe = dataclasses.replace(
        _probe(machine, tmp_path), env={"VIRTUAL_ENV": "/helper/env", "HOME": str(tmp_path)}
    )
    assert main(["update", str(project)], probe) == 0
    for command in (
        ("uv", "sync", "--directory", str(project)),
        *(command for command in machine.ran if command[3:5] == ("commit", "-m")),
    ):
        assert machine.envs[command] == {"HOME": str(tmp_path)}


@pytest.mark.parametrize("finished", [True, False])
def test_main_update_finish_merges_with_finish_branch(tmp_path: Path, *, finished: bool) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    finish = (
        "uv",
        "run",
        "--directory",
        str(project),
        "python",
        "tools/finish_branch.py",
        UPDATE_SUMMARY,
    )
    machine.answers[finish] = (0 if finished else 1, "")
    assert main(["update", str(project), "--finish"], _probe(machine, tmp_path)) == (
        0 if finished else 1
    )
    assert machine.ran[-1] == finish


def test_main_update_finish_with_nothing_new_finishes_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[UNCHANGED])
    assert main(["update", str(project), "--finish"], _probe(machine, tmp_path)) == 0
    assert not any("tools/finish_branch.py" in command for command in machine.ran)


@pytest.mark.parametrize(
    ("reason", "says"),
    [
        ("dirty", "uncommitted changes"),
        ("on another branch", "switch to main first"),
        ("no answers file", "not generated from these templates"),
    ],
)
def test_main_update_refuses_a_project_it_cannot_update_and_runs_no_copier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reason: str, says: str
) -> None:
    project = _project(tmp_path, BASE)
    machine = _updatable(project, BASE, after=[CHANGED])
    if reason == "dirty":
        machine.queued[_git(project, "status", "--porcelain")] = [(0, "?? notes.txt\n")]
    elif reason == "on another branch":
        machine.branch = "feat/fetch-retry"
    else:
        (project / BASE[0]).unlink()
    assert main(["update", str(project)], _probe(machine, tmp_path)) == 1
    assert not any(command[0] == "copier" for command in machine.ran)
    assert says in capsys.readouterr().err
