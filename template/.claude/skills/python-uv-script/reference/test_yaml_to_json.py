"""The yaml_to_json script: its pieces, then end to end through `main`, then one run on its own.

`scripts/` is importable because `pythonpath` in pyproject.toml lists the project root, so a
script's functions are called here directly, with literal arguments, as a debugger would.
"""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.yaml_to_json import load_yaml, main, to_json

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "yaml_to_json.py"
DOCUMENT = "name: demo\nports: [80, 443]\n"


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    path = tmp_path / "deploy.yaml"
    path.write_text(DOCUMENT, encoding="utf-8")
    return path


# --- the pieces ---------------------------------------------------------------------------


def test_load_yaml_reads_a_mapping(yaml_file: Path) -> None:
    assert load_yaml(yaml_file) == {"name": "demo", "ports": [80, 443]}


def test_to_json_sorts_keys_and_ends_with_a_newline() -> None:
    assert to_json({"b": 1, "a": [1, 2]}) == '{"a": [1, 2], "b": 1}\n'


# --- through main -------------------------------------------------------------------------


def test_main_writes_json_to_stdout_and_nothing_to_stderr(
    yaml_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(yaml_file)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"name": "demo", "ports": [80, 443]}
    assert captured.err == ""


def test_main_reports_a_missing_file_on_stderr_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.yaml"
    assert main([str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing.yaml" in captured.err


# --- the header ---------------------------------------------------------------------------


def test_the_script_runs_on_its_header_alone() -> None:
    """`--exact` rebuilds the script's own environment from the header, so a dependency that is
    only in the project's dev group fails here. The one subprocess in the suite: no import can
    prove this.
    """
    command = ["uv", "run", "--exact", str(SCRIPT), "--help"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    assert completed.returncode == 0, completed.stderr
