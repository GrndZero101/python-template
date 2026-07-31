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

import pytest
from pytest_copie.plugin import Copie

PROJECT_TYPES = ["cli-modern", "cli-stdlib", "fastapi", "tui", "data"]

# The example CLI travels only with cli-modern; every other type gets infrastructure and its
# own skill. Keep this table in step with `_exclude` in copier.yml.
SKILLS_BY_TYPE = {
    "cli-modern": {"python-cli", "python-cli-modern"},
    "cli-stdlib": {"python-cli", "python-cli-stdlib"},
    "fastapi": {"python-fastapi"},
    "tui": {"python-tui"},
    "data": {"python-data"},
}

BASE_ANSWERS = {
    "project_name": "Weather Tools",
    "package_name": "weather_tools",
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


def _generate(copie: Copie, project_type: str) -> Path:
    """Generate a project and return its directory, failing the test if copier did not."""
    result = copie.copy(extra_answers=_answers(project_type))
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.exit_code == 0, f"copier exited {result.exit_code}"
    assert result.project_dir is not None
    return result.project_dir


requires_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
requires_prek = pytest.mark.skipif(shutil.which("prek") is None, reason="prek is not installed")


# --- structure ----------------------------------------------------------------------------


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_package_directory_is_named_from_the_answer(copie: Copie, project_type: str) -> None:
    """`src/python_template/` was the template's own name and must not survive generation."""
    project = _generate(copie, project_type)
    assert (project / "src" / "weather_tools" / "__init__.py").is_file()
    assert not (project / "src" / "python_template").exists()


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_no_jinja_suffix_or_placeholder_survives(copie: Copie, project_type: str) -> None:
    """A leftover `.jinja` file or an unrendered `{{` means a substitution was missed."""
    project = _generate(copie, project_type)
    leftovers = sorted(path.name for path in project.rglob("*.jinja"))
    assert leftovers == []
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert "{{" not in pyproject
    assert 'name = "weather-tools"' in pyproject


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_only_the_matching_skills_ship(copie: Copie, project_type: str) -> None:
    project = _generate(copie, project_type)
    shipped = {path.name for path in (project / ".claude" / "skills").iterdir()}
    assert shipped == SKILLS_BY_TYPE[project_type]


@pytest.mark.parametrize("project_type", PROJECT_TYPES)
def test_example_cli_travels_only_with_cli_modern(copie: Copie, project_type: str) -> None:
    """Shipping the demo elsewhere would drag typer, httpx and rich into an unrelated stack."""
    project = _generate(copie, project_type)
    expected = project_type == "cli-modern"
    assert (project / "src" / "weather_tools" / "geo.py").is_file() is expected
    assert (project / "tests" / "test_geo.py").is_file() is expected
    assert (
        'cli = "weather_tools.cli:main"' in (project / "pyproject.toml").read_text(encoding="utf-8")
    ) is expected


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
    assert "package_name: weather_tools" in answers
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
def test_branch_guard_blocks_edits_on_main_in_a_generated_project(copie: Copie) -> None:
    """The guard ships as a literal file, so generation must not have broken its imports."""
    project = _generate(copie, "cli-modern")
    payload = json.dumps({"tool_input": {"file_path": str(project / "src" / "x.py")}})
    guard = subprocess.run(
        ["uv", "run", "python", "tools/branch_guard.py", "--protected", "main"],
        cwd=project,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard.returncode == 2
    assert "Refusing to edit" in guard.stderr
