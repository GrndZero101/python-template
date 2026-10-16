"""Generation test for the base template, on its own.

`template/` holds Jinja and has no `pyproject.toml`, so it cannot be linted, type-checked or run
where it sits — the check is to generate a project and run *that* project's own gate and test suite
inside it. This module does that for the base alone, the way a prototype or a brownfield repo adopts
it.

The base layered under a use case is checked by the use case's repository, python-template-cli-typer:
its suite generates through the CLI template and reads this repo's `copier.yml` and `template/`.
This repo's CI checks that repo out and runs its suite against the commit under test.

Not offline: generation runs `uv sync`, which reaches the network on a cold cache. Everything
else is deterministic — fixed answers, a fresh tmp directory per test, no clock and no rng.
"""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from pytest_copie.plugin import Copie

REPO_ROOT = Path(__file__).resolve().parent.parent

# What the base asks when it is applied on its own: the questions the two layers share.
SHARED_ANSWERS = {
    "project_name": "Weather Tools",
    "author_name": "A Dev",
    "author_email": "dev@example.com",
    "python_version": "3.14",
}

# What replaces a list in ruff-base.toml instead of adding to it. `extend-*` keys are the way in.
RUFF_REPLACING_KEYS = ("select", "ignore", "per-file-ignores", "unfixable")

# Every project gets these; a use case adds its own beside them.
BASE_SKILLS = {"git-workflow", "python-cli", "python-debug", "python-uv-script"}

# The uv-script skill's reference files, and where its recipe says to copy them.
UV_SCRIPT_REFERENCE = Path(".claude") / "skills" / "python-uv-script" / "reference"
SCRIPT_NAME = "yaml_to_json.py"
SCRIPT_TEST_NAME = "test_yaml_to_json.py"
# The line the type-error case breaks: `str + int`, which only ty can see.
BREAK_TARGET = 'sort_keys=True) + "\\n"'
GATE = ["prek", "run", "--all-files", "--skip", "no-commit-to-branch"]
TESTS = ["uv", "run", "python", "-m", "pytest", "-q"]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in `cwd` and capture it. Never a shell string — the portability rule."""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


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


def _requirement_names(requirements: list[str]) -> set[str]:
    """Return the distribution names in a list of requirement strings."""
    return {re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0] for requirement in requirements}


def _assert_pyproject_serves_the_base(pyproject: Path) -> None:
    """Fail unless `pyproject.toml` holds what the base's machinery relies on.

    ruff merges configs, so it extends the base's. pytest, ty and rumdl take the first config they
    find and merge nothing, so their settings repeat in each project and are checked here. This
    cannot be a test under tools/tests: one there never notices `tools/tests` leaving `testpaths`,
    because it then never runs. The CLI repo's suite holds the same check for its own pyproject.
    """
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    tool = config["tool"]
    pytest_options = tool["pytest"]["ini_options"]
    assert "error" in pytest_options["filterwarnings"], "a deprecation must fail the test"
    assert "tools/tests" in pytest_options["testpaths"], "the hooks' tests would never run"
    assert "tools" in pytest_options["pythonpath"], "the hooks' tests could not import them"
    assert "." in pytest_options["pythonpath"], (
        "a test could not import a uv script as scripts.<name>"
    )
    assert "tools" in tool["ty"]["environment"]["extra-paths"], "ty cannot resolve tools/"
    assert ".claude" in tool["ty"]["src"]["exclude"], "ty would check skill reference code"
    ruff = tool["ruff"]
    assert ruff.get("extend") == "ruff-base.toml", "ruff would not read the base's rules"
    replacing = [key for key in RUFF_REPLACING_KEYS if key in ruff or key in ruff.get("lint", {})]
    assert replacing == [], f"{replacing} would replace the base's list; use `extend-*`"
    dev = _requirement_names(config["dependency-groups"]["dev"])
    assert {"pytest", "debugpy"} <= dev, "the hooks run pytest and .debugmcp.json launches debugpy"


def _generate_base(copie: Copie) -> Path:
    """Generate the base alone with the shared answers and return the project directory."""
    result = copie.copy(extra_answers=SHARED_ANSWERS, template_dir=REPO_ROOT)
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.project_dir is not None
    return result.project_dir


def _gate_and_test(project: Path) -> None:
    """Stage everything, then require the project's whole gate and its tests to pass."""
    _run(["git", "add", "-A"], project)
    gate = _run(GATE, project)
    assert gate.returncode == 0, f"{gate.stdout}\n{gate.stderr}"
    tests = _run(TESTS, project)
    assert tests.returncode == 0, f"{tests.stdout}\n{tests.stderr}"


@requires_uv
@requires_prek
def test_the_base_alone_is_a_project_that_passes_its_gate(copie: Copie) -> None:
    """A prototype or a brownfield repo adopts the base with no use case: its fallback must hold."""
    project = _generate_base(copie)
    assert (project / ".copier-answers.base.yml").is_file()
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / "src").exists(), "the base alone must ship no source"
    shipped = {path.name for path in (project / ".claude" / "skills").iterdir()}
    assert shipped == BASE_SKILLS
    _assert_pyproject_serves_the_base(project / "pyproject.toml")
    _gate_and_test(project)


@requires_uv
@requires_prek
def test_uv_script_reference_passes_the_gate_where_the_recipe_puts_it(copie: Copie) -> None:
    """The python-uv-script recipe, followed literally; then a type error, to prove ty sees it.

    ty-pre-commit's `uv check` skips every file with a PEP 723 header, so the local hook that
    replaced it is checked the only way that means anything: a broken script must turn the gate
    red, naming the script.
    """
    project = _generate_base(copie)
    _run(["git", "switch", "--quiet", "-c", "feat/yaml-to-json"], project)
    added = _run(["uv", "add", "--dev", "pyyaml"], project)
    assert added.returncode == 0, added.stderr
    reference = project / UV_SCRIPT_REFERENCE
    scripts = project / "scripts"
    scripts.mkdir()
    (project / "tests").mkdir(exist_ok=True)
    shutil.copy(reference / SCRIPT_NAME, scripts / SCRIPT_NAME)
    shutil.copy(reference / SCRIPT_TEST_NAME, project / "tests" / SCRIPT_TEST_NAME)
    _gate_and_test(project)
    script = scripts / SCRIPT_NAME
    source = script.read_text(encoding="utf-8")
    assert BREAK_TARGET in source, "the reference has moved on; point BREAK_TARGET at a str line"
    script.write_text(source.replace(BREAK_TARGET, BREAK_TARGET + " + 1"), encoding="utf-8")
    broken = _run(GATE, project)
    report = f"{broken.stdout}\n{broken.stderr}"
    assert broken.returncode != 0, "a type error in a uv script passed the gate"
    assert f"scripts/{SCRIPT_NAME}" in report, report


@requires_uv
def test_a_blank_author_email_is_left_out(copie: Copie) -> None:
    """`email = ""` is not an address; an author with none gets no `email` key at all."""
    answers = {**SHARED_ANSWERS, "author_email": ""}
    result = copie.copy(extra_answers=answers, template_dir=REPO_ROOT)
    assert result.exception is None, f"copier raised: {result.exception}"
    assert result.project_dir is not None
    pyproject = (result.project_dir / "pyproject.toml").read_text(encoding="utf-8")
    authors = tomllib.loads(pyproject)["project"]["authors"]
    assert authors == [{"name": SHARED_ANSWERS["author_name"]}]
