"""Generation tests for the copier template.

These are the only thing that verifies `template/`. It holds Jinja expressions and no
`pyproject.toml`, so it cannot be linted, type-checked or run where it sits — the check is to
generate a project and then run *that* project's own gate and test suite inside it.

Not offline: generation runs `uv sync`, which reaches the network on a cold cache. Everything
else is deterministic — fixed answers, a fresh tmp directory per test, no clock and no rng.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_copie.plugin import Copie

REPO_ROOT = Path(__file__).resolve().parent.parent

PROJECT_TYPES = ["cli-modern", "cli-stdlib", "fastapi", "tui", "data"]

# The scaffold CLI travels only with cli-modern; every other type gets infrastructure and its
# own skill. The debugging skill is infrastructure, so every type gets it. Keep this table in
# step with `_exclude` in copier.yml.
SKILLS_BY_TYPE = {
    "cli-modern": {"python-cli", "python-cli-modern", "python-debug"},
    "cli-stdlib": {"python-cli", "python-cli-stdlib", "python-debug"},
    "fastapi": {"python-fastapi", "python-debug"},
    "tui": {"python-tui", "python-debug"},
    "data": {"python-data", "python-debug"},
}

# What each project type's src/ and tests/ hold. Keep in step with `_exclude` in copier.yml.
BASE_MODULES = {"__init__.py"}
CLI_MODULES = {
    "about.py",
    "cli.py",
    "config.py",
    "logging_setup.py",
    "options.py",
    "output.py",
    "typer_entrypoint.py",
}
BASE_TESTS = {
    "test_branch_guard.py",
    "test_check_nested_defs.py",
    "test_debug_module.py",
    "test_debug_pytest.py",
    "test_gate.py",
    "test_hook_payload.py",
}
CLI_TESTS = {"conftest.py", "test_about.py", "test_config.py", "test_typer_entrypoint.py"}

# DELIBERATELY LONGER than the template's own `python_template`. A shorter name cannot overflow
# a line that was formatted against the template's name, so it silently proves nothing: the
# suite passed for months against `weather_tools` (13 chars) while generation with a longer name
# produced a project that failed its own `ruff format` check on two files.
PACKAGE_NAME = "a_deliberately_long_package_name"
DIST_NAME = PACKAGE_NAME.replace("_", "-")
SCRIPT_NAME = "weather-tools"

BASE_ANSWERS = {
    "project_name": "Weather Tools",
    "package_name": PACKAGE_NAME,
    "script_name": SCRIPT_NAME,
    "project_description": "Look things up",
    "author_name": "A Dev",
    "author_email": "dev@example.com",
    "python_version": "3.14",
}


def _answers(project_type: str) -> dict[str, str]:
    """Return the full answer set for one project type."""
    return {**BASE_ANSWERS, "project_type": project_type}


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in `cwd` and capture it. Never a shell string — the portability rule."""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _generate(copie: Copie, project_type: str, template_dir: Path | None = None) -> Path:
    """Generate a project and return its directory, failing the test if copier did not.

    `template_dir` overrides the repo under test, which the update tests need so they can move
    the template forward without committing to the real one.
    """
    result = copie.copy(extra_answers=_answers(project_type), template_dir=template_dir)
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.exit_code == 0, f"copier exited {result.exit_code}"
    assert result.project_dir is not None
    return result.project_dir


requires_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
requires_prek = pytest.mark.skipif(shutil.which("prek") is None, reason="prek is not installed")
requires_copier = pytest.mark.skipif(shutil.which("copier") is None, reason="copier is not on PATH")


def _clone_template(destination: Path) -> Path:
    """Clone this repo so a test can commit to the template without touching the real one.

    `copier update` compares the commit recorded in `.copier-answers.yml` against a newer ref, so
    a meaningful test needs a template it can actually move forward. Only committed state is
    cloned, which is what a generated project would pull from anyway.
    """
    clone = destination / "template-clone"
    cloned = _run(["git", "clone", "--quiet", str(REPO_ROOT), str(clone)], destination)
    assert cloned.returncode == 0, cloned.stderr
    return clone


def _commit_all(repo: Path, message: str) -> None:
    """Commit everything in `repo`, bypassing hooks.

    `--no-verify` is deliberate. A *generated* project has its own guards installed and sits on
    `main`, so an ordinary commit is refused by `no-commit-to-branch` — which is the behaviour
    those guards exist for. These commits stand in for work a user already did; the guards
    themselves are tested separately.
    """
    _run(["git", "add", "-A"], repo)
    committed = _run(["git", "commit", "--no-verify", "-m", message], repo)
    assert committed.returncode == 0, committed.stdout + committed.stderr


# --- structure ----------------------------------------------------------------------------


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_package_directory_is_named_from_the_answer(copie: Copie, project_type: str) -> None:
    """`src/python_template/` was the template's own name and must not survive generation."""
    project = _generate(copie, project_type)
    assert (project / "src" / PACKAGE_NAME / "__init__.py").is_file()
    assert not (project / "src" / "python_template").exists()


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_no_jinja_suffix_or_placeholder_survives(copie: Copie, project_type: str) -> None:
    """A leftover `.jinja` file or an unrendered `{{` means a substitution was missed."""
    project = _generate(copie, project_type)
    leftovers = sorted(path.name for path in project.rglob("*.jinja"))
    assert leftovers == []
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert "{{" not in pyproject
    assert f'name = "{DIST_NAME}"' in pyproject


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_only_the_matching_skills_ship(copie: Copie, project_type: str) -> None:
    project = _generate(copie, project_type)
    shipped = {path.name for path in (project / ".claude" / "skills").iterdir()}
    assert shipped == SKILLS_BY_TYPE[project_type]


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
@pytest.mark.parametrize("adapter", ["python", "pytest"])
def test_debugmcp_adapter_points_at_a_shipped_program(
    copie: Copie, project_type: str, adapter: str
) -> None:
    """The DebugMCP CLI resolves `program` only when a session starts, so a renamed shim fails late.

    `${workspaceFolder}` is the session's working directory, which the skill says is the root.
    """
    project = _generate(copie, project_type)
    config = json.loads((project / ".debugmcp.json").read_text(encoding="utf-8"))
    program = config["adapters"][adapter]["launch"]["program"]
    relative = program.removeprefix("${workspaceFolder}/")
    assert (project / relative).is_file(), f"{program} does not exist in the generated project"


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_scaffold_cli_travels_only_with_cli_modern(copie: Copie, project_type: str) -> None:
    """Shipping it elsewhere would drag typer, rich and pydantic-settings into an unrelated stack.

    Compared as whole sets, so a module added to the template but missed in `_exclude` fails here
    rather than turning up unannounced in a FastAPI project.
    """
    project = _generate(copie, project_type)
    is_cli = project_type == "cli-modern"
    modules = {path.name for path in (project / "src" / PACKAGE_NAME).glob("*.py")}
    assert modules == (BASE_MODULES | CLI_MODULES if is_cli else BASE_MODULES)
    tests = {path.name for path in (project / "tests").glob("*.py")}
    assert tests == (BASE_TESTS | CLI_TESTS if is_cli else BASE_TESTS)
    assert (
        f'{SCRIPT_NAME} = "{PACKAGE_NAME}.cli:main"'
        in (project / "pyproject.toml").read_text(encoding="utf-8")
    ) is is_cli


def test_environment_prefix_follows_the_script_name(copie: Copie) -> None:
    """`weather-tools` must read `WEATHER_TOOLS_*`, not a prefix every generated project shares."""
    project = _generate(copie, "cli-modern")
    config = (project / "src" / PACKAGE_NAME / "config.py").read_text(encoding="utf-8")
    assert 'ENV_PREFIX = "WEATHER_TOOLS_"' in config


def test_console_script_is_never_named_cli(copie: Copie) -> None:
    """`cli` is a read-only PowerShell alias for `Clear-Item`, and an alias beats PATH.

    A script installed under that name is unreachable from the shell most Windows users are in,
    and every generated project would claim the same name in a shared environment.
    """
    project = _generate(copie, "cli-modern")
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert "\ncli = " not in pyproject
    assert f'{SCRIPT_NAME} = "{PACKAGE_NAME}.cli:main"' in pyproject


def test_fastapi_gets_its_lint_rules(copie: Copie) -> None:
    project = _generate(copie, "fastapi")
    assert '"FAST",' in (project / "pyproject.toml").read_text(encoding="utf-8")


def test_other_types_do_not_get_fastapi_lint_rules(copie: Copie) -> None:
    project = _generate(copie, "cli-modern")
    assert '"FAST",' not in (project / "pyproject.toml").read_text(encoding="utf-8")


# --- the generation tasks -----------------------------------------------------------------


@requires_uv
def test_generation_leaves_a_committed_repo_on_main(copie: Copie) -> None:
    """The tasks must commit before installing the shims, or the first commit is impossible."""
    project = _generate(copie, "cli-modern")
    assert (project / ".git").is_dir()
    branch = _run(["git", "branch", "--show-current"], project)
    assert branch.stdout.strip() == "main"
    status = _run(["git", "status", "--porcelain"], project)
    assert status.stdout.strip() == "", "copier update needs a clean tree"
    log = _run(["git", "log", "--oneline"], project)
    assert "generate project from python-template" in log.stdout


@requires_uv
def test_answers_file_is_written_for_copier_update(copie: Copie) -> None:
    project = _generate(copie, "cli-modern")
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert f"package_name: {PACKAGE_NAME}" in answers
    assert "project_type: cli-modern" in answers


# --- the generated project's own gate -----------------------------------------------------


@requires_uv
@requires_prek
@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_generated_project_passes_its_own_gate(copie: Copie, project_type: str) -> None:
    """The real test. `no-commit-to-branch` is skipped because generation leaves us on main."""
    project = _generate(copie, project_type)
    gate = _run(
        ["prek", "run", "--all-files", "--skip", "no-commit-to-branch"],
        project,
    )
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"


@requires_uv
@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_generated_project_passes_its_own_tests(copie: Copie, project_type: str) -> None:
    project = _generate(copie, project_type)
    tests = _run(["uv", "run", "python", "-m", "pytest", "-q"], project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"


@requires_uv
def test_debug_launcher_runs_a_source_module_with_relative_imports(copie: Copie) -> None:
    """The `python` adapter's `program`, run exactly as the DebugMCP CLI would launch it.

    Launched as a plain script instead, `cli.py` dies on its first relative import — and under the
    debugger that surfaces only as "ran to completion", which is how the defect went unnoticed.
    """
    project = _generate(copie, "cli-modern")
    cli = project / "src" / PACKAGE_NAME / "cli.py"
    launched = _run(["uv", "run", "python", "tools/debug_module.py", str(cli), "--help"], project)
    assert launched.returncode == 0, f"{launched.stdout}\n{launched.stderr}"
    assert SCRIPT_NAME in launched.stdout


# --- copier update ------------------------------------------------------------------------
#
# The reason copier was chosen over cookiecutter: an improvement to CLAUDE.md or a skill can be
# pulled into projects that already exist. These tests are what make that claim true rather than
# assumed. Each clones the repo so the template can be moved forward without touching the real one.
#
# UNLIKE EVERY OTHER TEST HERE, these see only COMMITTED state. `copier update` needs two real
# commits to diff between, so the clone cannot include the working tree the way `copie.copy()`
# does. A change to copier.yml that is not yet committed will not be under test.

MARKER = "A line added by the template after this project was generated."


@requires_uv
@requires_copier
def test_update_pulls_a_later_template_change_into_an_existing_project(
    copie: Copie, tmp_path: Path
) -> None:
    clone = _clone_template(tmp_path)
    project = _generate(copie, "cli-modern", template_dir=clone)
    assert MARKER not in (project / "CLAUDE.md").read_text(encoding="utf-8")

    claude_md = clone / "template" / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text(encoding="utf-8") + f"\n{MARKER}\n", encoding="utf-8")
    _commit_all(clone, "docs: add a marker line")

    updated = _run(["copier", "update", "--trust", "--defaults"], project)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert MARKER in (project / "CLAUDE.md").read_text(encoding="utf-8")


@requires_uv
@requires_copier
def test_update_preserves_a_file_the_project_has_edited(copie: Copie, tmp_path: Path) -> None:
    """The case that decides whether updating is safe: local work must not be silently lost."""
    clone = _clone_template(tmp_path)
    project = _generate(copie, "cli-modern", template_dir=clone)

    local_edit = "# A line this project added for itself.\n"
    readme = project / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + local_edit, encoding="utf-8")
    _commit_all(project, "docs: local change")

    template_readme = clone / "template" / "README.md.jinja"
    template_readme.write_text(
        template_readme.read_text(encoding="utf-8") + f"\n{MARKER}\n", encoding="utf-8"
    )
    _commit_all(clone, "docs: change the readme upstream")

    updated = _run(["copier", "update", "--trust", "--defaults"], project)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert local_edit in readme.read_text(encoding="utf-8"), "local work was discarded"


@requires_uv
@requires_prek
@requires_copier
def test_a_project_still_passes_its_gate_after_updating(copie: Copie, tmp_path: Path) -> None:
    clone = _clone_template(tmp_path)
    project = _generate(copie, "cli-modern", template_dir=clone)

    claude_md = clone / "template" / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text(encoding="utf-8") + f"\n{MARKER}\n", encoding="utf-8")
    _commit_all(clone, "docs: add a marker line")
    _run(["copier", "update", "--trust", "--defaults"], project)

    gate = _run(["prek", "run", "--all-files", "--skip", "no-commit-to-branch"], project)
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"


def _hooks(project: Path) -> list[dict[str, Any]]:
    """Return every command hook declared in a generated project's `.claude/settings.json`."""
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    found: list[dict[str, Any]] = []
    for groups in settings["hooks"].values():
        for group in groups:
            found.extend(group["hooks"])
    return found


def _hook_argv(project: Path, script: str) -> list[str]:
    """Return the argv Claude Code would spawn for the hook running `script`.

    Exec form substitutes `${CLAUDE_PROJECT_DIR}` as a plain string; doing the same here is what
    lets these tests run the shipped hook exactly as written rather than a copy of it.
    """
    for hook in _hooks(project):
        args = [str(arg) for arg in hook.get("args", [])]
        if script in args:
            resolved = [arg.replace("${CLAUDE_PROJECT_DIR}", str(project)) for arg in args]
            return [str(hook["command"]), *resolved]
    pytest.fail(f"no hook runs {script}")


def test_every_hook_is_exec_form(copie: Copie) -> None:
    """Exec form spawns the executable directly, so no hook can depend on a shell existing."""
    project = _generate(copie, "cli-modern")
    for hook in _hooks(project):
        assert isinstance(hook.get("args"), list), f"shell-form hook: {hook['command']}"
        assert " " not in str(hook["command"]), f"command is more than one word: {hook['command']}"


@requires_uv
def test_branch_guard_blocks_edits_on_main_in_a_generated_project(
    copie: Copie, tmp_path: Path
) -> None:
    """Run from elsewhere: an agent's `cd` must not stop the guard finding its script."""
    project = _generate(copie, "cli-modern")
    payload = json.dumps({"tool_input": {"file_path": str(project / "src" / "x.py")}})
    guard = subprocess.run(
        _hook_argv(project, "tools/branch_guard.py"),
        cwd=tmp_path,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard.returncode == 2, guard.stderr
    assert "Refusing to edit" in guard.stderr


@requires_uv
def test_branch_guard_survives_a_conflicted_pyproject(copie: Copie) -> None:
    """A copier update can leave markers in pyproject.toml; the guard must still run to allow
    the edit that resolves them."""
    project = _generate(copie, "cli-modern")
    _run(["git", "switch", "--quiet", "-c", "chore/update"], project)
    pyproject = project / "pyproject.toml"
    marker = "<" * 7 + " before updating\n"
    pyproject.write_text(marker + pyproject.read_text(encoding="utf-8"), encoding="utf-8")
    payload = json.dumps({"tool_input": {"file_path": str(pyproject)}})
    guard = subprocess.run(
        _hook_argv(project, "tools/branch_guard.py"),
        cwd=project,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard.returncode == 0, guard.stderr


@requires_uv
@requires_prek
def test_gate_pauses_while_conflict_markers_remain(copie: Copie) -> None:
    project = _generate(copie, "cli-modern")
    _run(["git", "switch", "--quiet", "-c", "chore/update"], project)
    readme = project / "README.md"
    conflict = "<" * 7 + " before updating\nold\n=======\nnew\n" + ">" * 7 + " after updating\n"
    readme.write_text(readme.read_text(encoding="utf-8") + conflict, encoding="utf-8")
    payload = json.dumps({"tool_input": {"file_path": str(project / "src" / "x.py")}})
    gate = subprocess.run(
        _hook_argv(project, "tools/gate.py"),
        cwd=project,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert gate.returncode == 2, gate.stderr
    assert "gate paused" in gate.stderr
    assert "README.md" in gate.stderr


@requires_prek
def test_commit_gate_catches_conflict_markers_outside_a_merge(copie: Copie) -> None:
    """check-merge-conflict only looks mid-merge by default, and a copier update is not one."""
    project = _generate(copie, "cli-modern")
    readme = project / "README.md"
    conflict = "<" * 7 + " before updating\nold\n=======\nnew\n" + ">" * 7 + " after updating\n"
    readme.write_text(readme.read_text(encoding="utf-8") + conflict, encoding="utf-8")
    hook = _run(["prek", "run", "check-merge-conflict", "--files", "README.md"], project)
    assert hook.returncode != 0, hook.stdout
