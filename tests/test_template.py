"""Generation tests for the copier templates.

These are the only thing that verifies `template/` (the base) and `use-cases/cli-typer/template/`
(the CLI layer). They hold Jinja expressions and no `pyproject.toml`, so they cannot be linted,
type-checked or run where they sit — the check is to generate a project and then run *that*
project's own gate and test suite inside it.

A project is made in two steps by one command: copying the use case renders its files, then its one
task copies the base over them. The tests below generate through the use case, as a user does, and
point `base_template` at this checkout so the base under test is the working tree.

Not offline: generation runs `uv sync`, which reaches the network on a cold cache. Everything
else is deterministic — fixed answers, a fresh tmp directory per test, no clock and no rng.
"""

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from pytest_copie.plugin import Copie

REPO_ROOT = Path(__file__).resolve().parent.parent
USE_CASE_DIR = REPO_ROOT / "use-cases" / "cli-typer"

# Every project gets every skill: data and TUI work are layered on the CLI, not chosen at generation.
SKILLS = {
    "git-workflow",
    "python-cli",
    "python-cli-typer",
    "python-data",
    "python-debug",
    "python-tui",
}

# What a generated project's src/ and tests/ hold, compared as whole sets.
MODULES = {
    "__init__.py",
    "about.py",
    "cli.py",
    "config.py",
    "config_file.py",
    "logging_setup.py",
    "options.py",
    "output.py",
    "typer_entrypoint.py",
}
# The template's machinery is tested under tools/tests/, the same for every type, so tests/ holds
# only the product's own suite.
TOOLS_TESTS = {
    "test_branch_guard.py",
    "test_check_conventions.py",
    "test_debug_module.py",
    "test_debug_pytest.py",
    "test_finish_branch.py",
    "test_gate.py",
    "test_gate_log.py",
    "test_hook_payload.py",
    "test_session_doctor.py",
    "test_stop_gate.py",
}
TESTS = {
    "conftest.py",
    "test_about.py",
    "test_config.py",
    "test_config_file.py",
    "test_logging_setup.py",
    "test_package.py",
    "test_typer_entrypoint.py",
}

# DELIBERATELY LONGER than the template's own `python_template`. A shorter name cannot overflow
# a line that was formatted against the template's name, so it silently proves nothing: the
# suite passed for months against `weather_tools` (13 chars) while generation with a longer name
# produced a project that failed its own `ruff format` check on two files.
PACKAGE_NAME = "a_deliberately_long_package_name"
DIST_NAME = PACKAGE_NAME.replace("_", "-")
SCRIPT_NAME = "weather-tools"

# The lowest `python_version` copier.yml offers. Every other test generates at the default.
PYTHON_FLOOR = "3.12"

# What the base asks when it is applied on its own: the questions the two layers share.
SHARED_ANSWERS = {
    "project_name": "Weather Tools",
    "author_name": "A Dev",
    "author_email": "dev@example.com",
    "python_version": "3.14",
}

BASE_ANSWERS = {
    "project_name": "Weather Tools",
    "package_name": PACKAGE_NAME,
    "script_name": SCRIPT_NAME,
    "project_description": "Look things up",
    "author_name": "A Dev",
    "author_email": "dev@example.com",
    "python_version": "3.14",
}


def _answers(python_version: str | None = None, **overrides: str) -> dict[str, str]:
    """Return the full answer set, optionally at another Python version or with other answers."""
    answers = dict(BASE_ANSWERS)
    if python_version is not None:
        answers["python_version"] = python_version
    answers.update(overrides)
    return answers


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in `cwd` and capture it. Never a shell string — the portability rule."""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _generate(
    copie: Copie,
    use_case_dir: Path | None = None,
    base_dir: Path | None = None,
    python_version: str | None = None,
    **overrides: str,
) -> Path:
    """Generate a project and return its directory, failing the test if copier did not.

    `use_case_dir` and `base_dir` override the two templates under test, which the update tests
    need so they can move either one forward without committing to the real repo.
    """
    answers = _answers(python_version, **overrides)
    answers["base_template"] = str(base_dir or REPO_ROOT)
    result = copie.copy(extra_answers=answers, template_dir=use_case_dir or USE_CASE_DIR)
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.exit_code == 0, f"copier exited {result.exit_code}"
    assert result.project_dir is not None
    return result.project_dir


# GitHub Actions sets CI=true. There a missing tool is a broken runner, not an optional extra, so
# the test runs and fails on it: skipping would let the suite go green having checked nothing.
ON_CI = os.environ.get("CI") == "true"


def _requires(tool: str) -> pytest.MarkDecorator:
    """Skip a test locally when `tool` is not on PATH, but never on CI."""
    return pytest.mark.skipif(
        shutil.which(tool) is None and not ON_CI, reason=f"{tool} is not on PATH"
    )


requires_uv = _requires("uv")
requires_prek = _requires("prek")
requires_copier = _requires("copier")


def _snapshot(source: Path, destination: Path, name: str, *pathspecs: str) -> Path:
    """Copy a template's working tree into a fresh git repo, so a test can commit to it.

    `copier update` compares the commit recorded in the answers file against a newer ref, so a
    meaningful test needs a template it can actually move forward, and one that is a git repo root:
    copier records no commit for a plain directory. A use case lives in a subdirectory here, so it
    needs this even though the base could be cloned. Uncommitted changes are included, because the
    pre-commit hook runs these tests before the commit that would hold them.
    """
    snapshot = destination / name
    snapshot.mkdir()
    listed = _run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *pathspecs],
        source,
    )
    assert listed.returncode == 0, listed.stderr
    for relative in filter(None, listed.stdout.split("\0")):
        origin = source / relative
        if not origin.is_file():  # staged for deletion, or a directory entry
            continue
        (snapshot / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, snapshot / relative)
    assert _run(["git", "init", "--quiet", "-b", "main"], snapshot).returncode == 0
    _commit_all(snapshot, "chore: snapshot the template under test")
    return snapshot


def _snapshot_base(destination: Path) -> Path:
    """Snapshot the base template: `copier.yml` and everything it generates from."""
    return _snapshot(REPO_ROOT, destination, "base-snapshot", "copier.yml", "template")


def _snapshot_use_case(destination: Path) -> Path:
    """Snapshot the CLI use case, which becomes its own repo's root once it is split out."""
    return _snapshot(USE_CASE_DIR, destination, "use-case-snapshot")


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


def test_package_directory_is_named_from_the_answer(copie: Copie) -> None:
    """`src/python_template/` was the template's own name and must not survive generation."""
    project = _generate(copie)
    assert (project / "src" / PACKAGE_NAME / "__init__.py").is_file()
    assert not (project / "src" / "python_template").exists()


def test_no_jinja_suffix_or_placeholder_survives(copie: Copie) -> None:
    """A leftover `.jinja` file or an unrendered `{{` means a substitution was missed."""
    project = _generate(copie)
    leftovers = sorted(path.name for path in project.rglob("*.jinja"))
    assert leftovers == []
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert "{{" not in pyproject
    assert f'name = "{DIST_NAME}"' in pyproject


def test_every_skill_ships(copie: Copie) -> None:
    project = _generate(copie)
    shipped = {path.name for path in (project / ".claude" / "skills").iterdir()}
    assert shipped == SKILLS


def test_the_use_case_rules_ship_beside_the_base_claude_md(copie: Copie) -> None:
    """The base's CLAUDE.md points at `.claude/rules/`; the typer rows live there, not in the base."""
    project = _generate(copie)
    rules = (project / ".claude" / "rules" / "cli-typer.md").read_text(encoding="utf-8")
    base = (project / "CLAUDE.md").read_text(encoding="utf-8")
    for rule in ("raw-httpx-client", "patched-httpx", "typer-default", "run_screen"):
        assert rule in rules, f"{rule} should be stated in the use case's rules"
        assert rule not in base, f"{rule} names a stack the base must not know"


@pytest.mark.parametrize("adapter", ["python", "pytest"])
def test_debugmcp_adapter_points_at_a_shipped_program(copie: Copie, adapter: str) -> None:
    """The DebugMCP CLI resolves `program` only when a session starts, so a renamed shim fails late.

    `${workspaceFolder}` is the session's working directory, which the skill says is the root.
    """
    project = _generate(copie)
    config = json.loads((project / ".debugmcp.json").read_text(encoding="utf-8"))
    program = config["adapters"][adapter]["launch"]["program"]
    relative = program.removeprefix("${workspaceFolder}/")
    assert (project / relative).is_file(), f"{program} does not exist in the generated project"


def test_package_and_tests_hold_exactly_the_scaffold(copie: Copie) -> None:
    """Compared as whole sets, so a module added to the template but not here fails loudly."""
    project = _generate(copie)
    modules = {path.name for path in (project / "src" / PACKAGE_NAME).glob("*.py")}
    assert modules == MODULES
    tests = {path.name for path in (project / "tests").glob("*.py")}
    assert tests == TESTS
    tools_tests = {path.name for path in (project / "tools" / "tests").glob("*.py")}
    assert tools_tests == TOOLS_TESTS


def test_environment_prefix_follows_the_script_name(copie: Copie) -> None:
    """`weather-tools` must read `WEATHER_TOOLS_*`, not a prefix every generated project shares."""
    project = _generate(copie)
    config = (project / "src" / PACKAGE_NAME / "config.py").read_text(encoding="utf-8")
    assert 'ENV_PREFIX = "WEATHER_TOOLS_"' in config


def test_console_script_is_never_named_cli(copie: Copie) -> None:
    """`cli` is a read-only PowerShell alias for `Clear-Item`, and an alias beats PATH.

    A script installed under that name is unreachable from the shell most Windows users are in,
    and every generated project would claim the same name in a shared environment.
    """
    project = _generate(copie)
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert "\ncli = " not in pyproject
    assert f'{SCRIPT_NAME} = "{PACKAGE_NAME}.cli:main"' in pyproject


# --- the generation tasks -----------------------------------------------------------------


@requires_uv
def test_generation_leaves_a_committed_repo_on_main(copie: Copie) -> None:
    """The tasks must commit before installing the shims, or the first commit is impossible."""
    project = _generate(copie)
    assert (project / ".git").is_dir()
    branch = _run(["git", "branch", "--show-current"], project)
    assert branch.stdout.strip() == "main"
    status = _run(["git", "status", "--porcelain"], project)
    assert status.stdout.strip() == "", "copier update needs a clean tree"
    log = _run(["git", "log", "--oneline"], project)
    assert "generate project from python-template" in log.stdout


@requires_uv
def test_each_layer_writes_its_own_answers_file(copie: Copie) -> None:
    """Two templates on one project need two answers files, or each overwrites the other's."""
    project = _generate(copie)
    use_case = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert f"package_name: {PACKAGE_NAME}" in use_case
    base = (project / ".copier-answers.base.yml").read_text(encoding="utf-8")
    assert "package_name" not in base, "the base recorded a question it does not ask"
    assert "author_name: A Dev" in base, "the base should have read the use case's answers"


@requires_uv
def test_the_use_case_keeps_the_pyproject_it_wrote(copie: Copie) -> None:
    """The base's fallback pyproject.toml is `_skip_if_exists`; if it won, the CLI would be gone."""
    project = _generate(copie)
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert f'{SCRIPT_NAME} = "{PACKAGE_NAME}.cli:main"' in pyproject
    assert 'extend = "ruff-base.toml"' in pyproject
    assert (project / "ruff-base.toml").is_file()


@requires_uv
@requires_prek
def test_the_base_alone_is_a_project_that_passes_its_gate(copie: Copie) -> None:
    """A prototype or a brownfield repo adopts the base with no use case: its fallback must hold."""
    result = copie.copy(extra_answers=SHARED_ANSWERS, template_dir=REPO_ROOT)
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.project_dir is not None
    project = result.project_dir
    assert (project / ".copier-answers.base.yml").is_file()
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / "src").exists(), "the base alone must ship no source"
    _assert_pyproject_serves_the_base(project / "pyproject.toml")
    gate = _run(["prek", "run", "--all-files", "--skip", "no-commit-to-branch"], project)
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"
    tests = _run(["uv", "run", "python", "-m", "pytest", "-q"], project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"


# --- the licence ---------------------------------------------------------------------------

HOLDER = "Acme Ltd"
# A phrase only that licence's text contains, and the SPDX id pyproject.toml should carry.
LICENCE_MARKERS = {
    "MIT": ("Permission is hereby granted, free of charge", "MIT"),
    "Apache-2.0": ("Apache License\n", "Apache-2.0"),
    "Proprietary": ("All rights reserved.", "LicenseRef-Proprietary"),
}


def _recorded_year(project: Path) -> str:
    """Return the year the answers file locked in, which must look like a year."""
    year = str(_load_yaml(project / ".copier-answers.yml")["copyright_year"])
    assert re.fullmatch(r"\d{4}", year), f"copyright_year is {year!r}"
    return year


@requires_uv
@pytest.mark.parametrize("licence", sorted(LICENCE_MARKERS))
def test_the_licence_follows_the_answers(copie: Copie, licence: str) -> None:
    """D14: a generated project names its own holder and licence, never the template author's."""
    project = _generate(copie, license=licence, copyright_holder=HOLDER)
    text = (project / "LICENSE").read_text(encoding="utf-8")
    marker, spdx = LICENCE_MARKERS[licence]
    assert marker in text
    assert f"{_recorded_year(project)} {HOLDER}" in text
    assert "GrndZero101" not in text
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert f'license = "{spdx}"' in pyproject
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "(LICENSE)" in readme
    assert (licence in readme) or licence == "Proprietary"


@requires_uv
def test_the_holder_defaults_to_the_author_and_the_licence_to_mit(copie: Copie) -> None:
    project = _generate(copie)
    text = (project / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n\nCopyright (c) ")
    assert f"{_recorded_year(project)} {BASE_ANSWERS['author_name']}" in text


@requires_uv
@requires_copier
def test_update_keeps_the_year_it_recorded(copie: Copie, tmp_path: Path) -> None:
    """A computed answer is recomputed on every update unless the recipe locks it (D14).

    The answers file is edited to a year the clock cannot produce, so a recomputed year is
    distinguishable from a kept one without waiting for New Year.
    """
    base = _snapshot_base(tmp_path)
    project = _generate(copie, base_dir=base)
    for name in (".copier-answers.yml", ".copier-answers.base.yml"):
        answers = project / name
        year = _recorded_year(project)
        answers.write_text(
            answers
            .read_text(encoding="utf-8")
            .replace(f"copyright_year: '{year}'", "copyright_year: '1999'")
            .replace(f"copyright_year: {year}", "copyright_year: '1999'"),
            encoding="utf-8",
        )
    _commit_all(project, "chore: pretend the project is old")
    _append(base / "template" / "CLAUDE.md", f"\n{MARKER}\n")
    _commit_all(base, "docs: add a marker line")

    updated = _run(UPDATE_BASE, project)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert "1999" in (project / "LICENSE").read_text(encoding="utf-8")
    assert "copyright_year: '1999'" in (project / ".copier-answers.base.yml").read_text(
        encoding="utf-8"
    )


# --- the contract between the layers ------------------------------------------------------
#
# Two templates on one project only work if they stay apart where they must and agree where they
# share. These are the three ways that breaks, each caught here rather than by a user's update.


def _rendered_paths(template: Path) -> set[str]:
    """Return the paths a template would generate: its files, minus the `.jinja` suffix."""
    return {
        path.relative_to(template).as_posix().removesuffix(".jinja")
        for path in template.rglob("*")
        if path.is_file()
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_layers_render_no_file_in_common() -> None:
    """A path both layers render conflicts on update, with markers in the file.

    Only what the base lists under `_skip_if_exists` may overlap: copier never overwrites it and
    leaves it out of the update patch, so the use case's version always wins.
    """
    base = _rendered_paths(REPO_ROOT / "template")
    use_case = _rendered_paths(USE_CASE_DIR / "template")
    skipped = set(_load_yaml(REPO_ROOT / "copier.yml")["_skip_if_exists"])
    shared = (base & use_case) - skipped
    assert shared == set(), f"rendered by both layers: {sorted(shared)}; give each file one owner"
    assert skipped <= use_case, "a `_skip_if_exists` file the use case does not write is not shared"


def _questions(copier_yml: Path) -> dict[str, dict[str, Any]]:
    """Return a template's questions: every top-level key not starting with an underscore."""
    config = _load_yaml(copier_yml)
    return {key: value for key, value in config.items() if not key.startswith("_")}


def test_the_layers_define_the_shared_questions_alike() -> None:
    """The base asks what the use case did not, so a drift here asks a user twice or not at all.

    The base falls back to a use case's answer, so its `default` differs by design; what must
    agree is the question itself: its type, its help text and its choices.
    """
    base = _questions(REPO_ROOT / "copier.yml")
    use_case = _questions(USE_CASE_DIR / "copier.yml")
    missing = sorted(set(base) - set(use_case))
    assert missing == [], f"base questions the use case does not ask: {missing}"
    for name, question in base.items():
        for key in ("type", "help", "choices"):
            assert question.get(key) == use_case[name].get(key), f"{name}: `{key}` differs"


@requires_uv
def test_the_answers_files_agree_on_the_shared_questions(copie: Copie) -> None:
    """Generated, the base must have recorded exactly what the use case did."""
    project = _generate(copie)
    base = _load_yaml(project / ".copier-answers.base.yml")
    use_case = _load_yaml(project / ".copier-answers.yml")
    shared = {key for key in base if not key.startswith("_")}
    assert shared == set(_questions(REPO_ROOT / "copier.yml"))
    for name in sorted(shared):
        assert base[name] == use_case[name], (
            f"{name}: base {base[name]!r}, use case {use_case[name]!r}"
        )


# What replaces a list in ruff-base.toml instead of adding to it. `extend-*` keys are the way in.
RUFF_REPLACING_KEYS = ("select", "ignore", "per-file-ignores", "unfixable")


def _requirement_names(requirements: list[str]) -> set[str]:
    """Return the distribution names in a list of requirement strings."""
    return {re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0] for requirement in requirements}


def _assert_pyproject_serves_the_base(pyproject: Path) -> None:
    """Fail unless `pyproject.toml` holds what the base's machinery relies on.

    ruff merges configs, so it extends the base's. pytest, ty and rumdl take the first config they
    find and merge nothing, so their settings repeat in each project and are checked here. This
    cannot be a test under tools/tests: one there never notices `tools/tests` leaving `testpaths`,
    because it then never runs.
    """
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    tool = config["tool"]
    pytest_options = tool["pytest"]["ini_options"]
    assert "error" in pytest_options["filterwarnings"], "a deprecation must fail the test"
    assert "tools/tests" in pytest_options["testpaths"], "the hooks' tests would never run"
    assert "tools" in pytest_options["pythonpath"], "the hooks' tests could not import them"
    assert "tools" in tool["ty"]["environment"]["extra-paths"], "ty cannot resolve tools/"
    assert ".claude" in tool["ty"]["src"]["exclude"], "ty would check skill reference code"
    ruff = tool["ruff"]
    assert ruff.get("extend") == "ruff-base.toml", "ruff would not read the base's rules"
    replacing = [key for key in RUFF_REPLACING_KEYS if key in ruff or key in ruff.get("lint", {})]
    assert replacing == [], f"{replacing} would replace the base's list; use `extend-*`"
    dev = _requirement_names(config["dependency-groups"]["dev"])
    assert {"pytest", "debugpy"} <= dev, "the hooks run pytest and .debugmcp.json launches debugpy"


@requires_uv
def test_the_use_case_pyproject_holds_what_the_base_relies_on(copie: Copie) -> None:
    project = _generate(copie)
    _assert_pyproject_serves_the_base(project / "pyproject.toml")


# --- the generated project's own gate -----------------------------------------------------


@requires_uv
@requires_prek
def test_generated_project_passes_its_own_gate(copie: Copie) -> None:
    """The real test. `no-commit-to-branch` is skipped because generation leaves us on main."""
    project = _generate(copie)
    gate = _run(
        ["prek", "run", "--all-files", "--skip", "no-commit-to-branch"],
        project,
    )
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"


@requires_uv
def test_generated_project_passes_its_own_tests(copie: Copie) -> None:
    project = _generate(copie)
    tests = _run(["uv", "run", "python", "-m", "pytest", "-q"], project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"


def test_python_version_file_follows_the_answer(copie: Copie) -> None:
    """`.python-version` picks the venv's interpreter and ty's target, so it must be the floor."""
    project = _generate(copie, python_version=PYTHON_FLOOR)
    assert (project / ".python-version").read_text(encoding="utf-8").strip() == PYTHON_FLOOR
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert f'requires-python = ">={PYTHON_FLOOR}"' in pyproject


@requires_uv
@requires_prek
def test_generated_project_works_at_the_python_floor(copie: Copie) -> None:
    """A project that declares the floor must pass its gate and tests running on it.

    Without this, answering an older version produced a project that passed everything on 3.14
    and then failed at import on the version it claimed to support. ty targets `.python-version`,
    so the gate here also rejects an API the floor does not have.
    """
    project = _generate(copie, python_version=PYTHON_FLOOR)
    gate = _run(["prek", "run", "--all-files", "--skip", "no-commit-to-branch"], project)
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"
    tests = _run(["uv", "run", "python", "-m", "pytest", "-q"], project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"
    version = _run(["uv", "run", "python", "--version"], project)
    assert version.stdout.startswith(f"Python {PYTHON_FLOOR}."), version.stdout


# The skills' reference files, and where their recipes say to copy them.
SKILLS_DIR = Path(".claude") / "skills"
REFERENCE_DIR = SKILLS_DIR / "python-cli-typer" / "reference"
REFERENCE_MODULES = ["http_client.py", "status.py"]
REFERENCE_TESTS = ["test_http_client.py", "test_status.py"]
DATA_REFERENCE_DIR = SKILLS_DIR / "python-data" / "reference"
TUI_REFERENCE_DIR = SKILLS_DIR / "python-tui" / "reference"
# The scaffold line the "add a command" recipe's registration goes beside.
COMMAND_ANCHOR = 'app.command("about")(about_command)\n'


def _register_command(cli: Path, name: str) -> None:
    """Make the recipe's two-line edit to cli.py, failing loudly if the scaffold has moved on.

    The import goes where isort would put it, among the other relative imports, so the gate's
    `--fix` has nothing to rewrite.
    """
    lines = cli.read_text(encoding="utf-8").splitlines(keepends=True)
    assert COMMAND_ANCHOR in lines, f"cli.py no longer has {COMMAND_ANCHOR!r}; update the recipes"
    lines.insert(lines.index(COMMAND_ANCHOR) + 1, f'app.command("{name}")({name}_command)\n')
    relative = [index for index, line in enumerate(lines) if line.startswith("from .")]
    assert relative, "cli.py has no relative imports; update the skills' recipes"
    new_import = f"from .{name} import {name}_command\n"
    later = [index for index in relative if lines[index] > new_import]
    lines.insert(later[0] if later else relative[-1] + 1, new_import)
    cli.write_text("".join(lines), encoding="utf-8")


def _gate_and_test(project: Path) -> None:
    """Stage everything, then require the project's whole gate and its tests to pass."""
    _run(["git", "add", "-A"], project)
    gate = _run(["prek", "run", "--all-files", "--skip", "no-commit-to-branch"], project)
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"
    tests = _run(["uv", "run", "python", "-m", "pytest", "-q"], project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"


@requires_uv
@requires_prek
def test_skill_reference_code_passes_the_gate_where_the_recipe_puts_it(copie: Copie) -> None:
    """Skill code is checked code: follow the recipe literally, then run the project's gate.

    Every defect phase 1 found in a skill was an example nobody had run. These files are meant to
    be copied unchanged, so they must pass the gate and their own tests exactly as shipped.
    """
    project = _generate(copie)
    _run(["git", "switch", "--quiet", "-c", "feat/status"], project)
    added = _run(["uv", "add", "httpx"], project)
    assert added.returncode == 0, added.stderr
    reference = project / REFERENCE_DIR
    for name in REFERENCE_MODULES:
        shutil.copy(reference / name, project / "src" / PACKAGE_NAME / name)
    for name in REFERENCE_TESTS:
        shutil.copy(reference / name, project / "tests" / name)
    _register_command(project / "src" / PACKAGE_NAME / "cli.py", "status")
    _gate_and_test(project)


@requires_uv
@requires_prek
def test_data_reference_code_passes_the_gate_where_the_recipe_puts_it(copie: Copie) -> None:
    """The python-data skill's "add a data command" recipe, followed literally."""
    project = _generate(copie)
    _run(["git", "switch", "--quiet", "-c", "feat/summary"], project)
    added = _run(["uv", "add", "polars"], project)
    assert added.returncode == 0, added.stderr
    reference = project / DATA_REFERENCE_DIR
    shutil.copy(reference / "summary.py", project / "src" / PACKAGE_NAME / "summary.py")
    shutil.copy(reference / "test_summary.py", project / "tests" / "test_summary.py")
    _register_command(project / "src" / PACKAGE_NAME / "cli.py", "summary")
    _gate_and_test(project)


@requires_uv
@requires_prek
def test_tui_reference_code_passes_the_gate_where_the_recipe_puts_it(copie: Copie) -> None:
    """The python-tui skill's "add a TUI command" recipe, followed literally."""
    project = _generate(copie)
    _run(["git", "switch", "--quiet", "-c", "feat/browse"], project)
    for command in (
        ["uv", "add", "textual"],
        ["uv", "add", "--dev", "pytest-asyncio", "textual-dev"],
    ):
        added = _run(command, project)
        assert added.returncode == 0, added.stderr
    reference = project / TUI_REFERENCE_DIR
    for name in ("rows.py", "browse.py"):
        shutil.copy(reference / name, project / "src" / PACKAGE_NAME / name)
    for name in ("test_rows.py", "test_browse.py"):
        shutil.copy(reference / name, project / "tests" / name)
    _register_command(project / "src" / PACKAGE_NAME / "cli.py", "browse")
    _gate_and_test(project)


@requires_uv
def test_debug_launcher_runs_a_source_module_with_relative_imports(copie: Copie) -> None:
    """The `python` adapter's `program`, run exactly as the DebugMCP CLI would launch it.

    Launched as a plain script instead, `cli.py` dies on its first relative import — and under the
    debugger that surfaces only as "ran to completion", which is how the defect went unnoticed.
    """
    project = _generate(copie)
    cli = project / "src" / PACKAGE_NAME / "cli.py"
    launched = _run(["uv", "run", "python", "tools/debug_module.py", str(cli), "--help"], project)
    assert launched.returncode == 0, f"{launched.stdout}\n{launched.stderr}"
    assert SCRIPT_NAME in launched.stdout


# --- copier update ------------------------------------------------------------------------
#
# The reason copier was chosen over cookiecutter: an improvement to CLAUDE.md or a skill can be
# pulled into projects that already exist. These tests are what make that claim true rather than
# assumed. Each snapshots a template into a throwaway git repo, so it can be moved forward without
# touching the real one. The snapshot includes uncommitted changes (see `_snapshot`); the commits
# the test makes on top of it are what `copier update` diffs.
#
# Two layers means two updates: `copier update -a .copier-answers.base.yml` for the base, a plain
# `copier update` for the use case. Each needs a clean tree and each touches only its own files.

MARKER = "A line added by the template after this project was generated."


UPDATE_BASE = ["copier", "update", "--trust", "--defaults", "-a", ".copier-answers.base.yml"]
UPDATE_USE_CASE = ["copier", "update", "--trust", "--defaults"]


def _append(path: Path, text: str) -> None:
    """Append `text` to a file, as a template author's edit would."""
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


@requires_uv
@requires_copier
def test_update_pulls_a_later_base_change_into_an_existing_project(
    copie: Copie, tmp_path: Path
) -> None:
    base = _snapshot_base(tmp_path)
    project = _generate(copie, base_dir=base)
    assert MARKER not in (project / "CLAUDE.md").read_text(encoding="utf-8")

    _append(base / "template" / "CLAUDE.md", f"\n{MARKER}\n")
    _commit_all(base, "docs: add a marker line")

    updated = _run(UPDATE_BASE, project)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert MARKER in (project / "CLAUDE.md").read_text(encoding="utf-8")


@requires_uv
@requires_copier
def test_update_preserves_a_file_the_project_has_edited(copie: Copie, tmp_path: Path) -> None:
    """The case that decides whether updating is safe: local work must not be silently lost."""
    use_case = _snapshot_use_case(tmp_path)
    project = _generate(copie, use_case_dir=use_case)

    local_edit = "# A line this project added for itself.\n"
    readme = project / "README.md"
    _append(readme, local_edit)
    _commit_all(project, "docs: local change")

    _append(use_case / "template" / "README.md.jinja", f"\n{MARKER}\n")
    _commit_all(use_case, "docs: change the readme upstream")

    updated = _run(UPDATE_USE_CASE, project)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert local_edit in readme.read_text(encoding="utf-8"), "local work was discarded"


@requires_uv
@requires_copier
def test_each_layer_updates_only_its_own_files(copie: Copie, tmp_path: Path) -> None:
    """D12's claim: a base fix reaches a project without a use-case release, and the reverse."""
    base = _snapshot_base(tmp_path)
    use_case = _snapshot_use_case(tmp_path)
    project = _generate(copie, use_case_dir=use_case, base_dir=base)

    _append(base / "template" / "CLAUDE.md", f"\n{MARKER}\n")
    _commit_all(base, "docs: change the base")
    _append(use_case / "template" / "README.md.jinja", f"\n{MARKER}\n")
    _commit_all(use_case, "docs: change the use case")
    claude_md = project / "CLAUDE.md"
    readme = project / "README.md"

    base_update = _run(UPDATE_BASE, project)
    assert base_update.returncode == 0, base_update.stdout + base_update.stderr
    assert MARKER in claude_md.read_text(encoding="utf-8")
    assert MARKER not in readme.read_text(encoding="utf-8"), "a base update touched the use case"

    _commit_all(project, "chore: apply the base update")
    use_case_update = _run(UPDATE_USE_CASE, project)
    assert use_case_update.returncode == 0, use_case_update.stdout + use_case_update.stderr
    assert MARKER in readme.read_text(encoding="utf-8")


@requires_uv
@requires_prek
@requires_copier
def test_a_project_still_passes_its_gate_after_updating(copie: Copie, tmp_path: Path) -> None:
    base = _snapshot_base(tmp_path)
    project = _generate(copie, base_dir=base)

    _append(base / "template" / "CLAUDE.md", f"\n{MARKER}\n")
    _commit_all(base, "docs: add a marker line")
    _run(UPDATE_BASE, project)

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
    project = _generate(copie)
    for hook in _hooks(project):
        assert isinstance(hook.get("args"), list), f"shell-form hook: {hook['command']}"
        assert " " not in str(hook["command"]), f"command is more than one word: {hook['command']}"


@requires_uv
def test_branch_guard_blocks_edits_on_main_in_a_generated_project(
    copie: Copie, tmp_path: Path
) -> None:
    """Run from elsewhere: an agent's `cd` must not stop the guard finding its script."""
    project = _generate(copie)
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
    project = _generate(copie)
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
    project = _generate(copie)
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


@requires_uv
@requires_prek
def test_stop_gate_refuses_once_to_end_a_turn_on_an_unchecked_file(copie: Copie) -> None:
    """A file written by a heredoc never passes PostToolUse; the Stop hook must still catch it."""
    project = _generate(copie)
    _run(["git", "switch", "--quiet", "-c", "feat/probe"], project)
    module = project / "src" / PACKAGE_NAME / "probe.py"
    module.write_text(
        '"""Probe."""\n\n\ndef f() -> str:\n    """F."""\n    return 1\n', encoding="utf-8"
    )
    argv = _hook_argv(project, "tools/stop_gate.py")
    first = subprocess.run(
        argv,
        cwd=project,
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 2, first.stdout + first.stderr
    assert "invalid-return-type" in first.stderr
    again = subprocess.run(
        argv,
        cwd=project,
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": True}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode == 0, "a second stop must always be allowed"


@requires_uv
def test_session_doctor_reports_a_missing_shim_in_a_generated_project(copie: Copie) -> None:
    """Every guard fails open; this hook is the only place a switched-off one becomes visible."""
    project = _generate(copie)
    argv = _hook_argv(project, "tools/session_doctor.py")
    healthy = _run(argv, project)
    assert healthy.returncode == 0, healthy.stderr
    assert healthy.stdout.startswith("## main"), healthy.stdout
    (project / ".git" / "hooks" / "commit-msg").unlink()
    broken = _run(argv, project)
    assert broken.returncode == 0, broken.stderr
    assert "commit-msg" in json.loads(broken.stdout)["systemMessage"]


@requires_prek
def test_commit_gate_catches_conflict_markers_outside_a_merge(copie: Copie) -> None:
    """check-merge-conflict only looks mid-merge by default, and a copier update is not one."""
    project = _generate(copie)
    readme = project / "README.md"
    conflict = "<" * 7 + " before updating\nold\n=======\nnew\n" + ">" * 7 + " after updating\n"
    readme.write_text(readme.read_text(encoding="utf-8") + conflict, encoding="utf-8")
    hook = _run(["prek", "run", "check-merge-conflict", "--files", "README.md"], project)
    assert hook.returncode != 0, hook.stdout
