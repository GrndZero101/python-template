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
    assert "tools" in tool["ty"]["environment"]["extra-paths"], "ty cannot resolve tools/"
    assert ".claude" in tool["ty"]["src"]["exclude"], "ty would check skill reference code"
    ruff = tool["ruff"]
    assert ruff.get("extend") == "ruff-base.toml", "ruff would not read the base's rules"
    replacing = [key for key in RUFF_REPLACING_KEYS if key in ruff or key in ruff.get("lint", {})]
    assert replacing == [], f"{replacing} would replace the base's list; use `extend-*`"
    dev = _requirement_names(config["dependency-groups"]["dev"])
    assert {"pytest", "debugpy"} <= dev, "the hooks run pytest and .debugmcp.json launches debugpy"


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
