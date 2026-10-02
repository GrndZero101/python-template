"""Tests for the module launcher the DebugMCP CLI's `python` adapter runs as its `program`.

The mapping and dispatch tests inject the runners. The round trips use the real `runpy` against
files written to `tmp_path`, so they prove relative imports and `__name__` actually work.
"""

import functools
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from debug_module import USAGE, Target, main, resolve

FIXTURE_PACKAGE = "debug_module_fixture_pkg"


def _recording_run(calls: list[tuple[str, dict[str, Any]]], name: str, **kwargs: Any) -> None:
    """Stand in for a runpy runner: record what it was asked to run."""
    calls.append((name, kwargs))


def _write(path: Path, text: str) -> Path:
    """Create `path`, and its parents, holding `text`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def isolated_sys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let `main` rewrite `sys.argv` and `sys.path` without leaking into later tests."""
    monkeypatch.setattr(sys, "argv", ["debug_module.py"])
    monkeypatch.setattr(sys, "path", list(sys.path))


@pytest.fixture
def fixture_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A `src/` holding a package whose entry module uses a relative import, made importable."""
    src = tmp_path / "src"
    package = src / FIXTURE_PACKAGE
    _write(package / "__init__.py", "")
    _write(package / "helper.py", "GREETING = 'from a relative import'\n")
    _write(
        package / "cli.py",
        "import sys\n"
        "from pathlib import Path\n"
        "from .helper import GREETING\n"
        "if __name__ == '__main__':\n"
        "    Path(sys.argv[1]).write_text(GREETING, encoding='utf-8')\n",
    )
    monkeypatch.syspath_prepend(str(src))
    yield src
    for name in [key for key in sys.modules if key.startswith(FIXTURE_PACKAGE)]:
        del sys.modules[name]


def test_maps_a_package_module_to_its_dotted_name(tmp_path: Path) -> None:
    file = _write(tmp_path / "src" / "pkg" / "cli.py", "")
    assert resolve(file, tmp_path / "src") == Target(path=file.resolve(), module="pkg.cli")


def test_maps_a_subpackage_module(tmp_path: Path) -> None:
    file = _write(tmp_path / "src" / "pkg" / "sub" / "mod.py", "")
    assert resolve(file, tmp_path / "src").module == "pkg.sub.mod"


def test_a_file_outside_src_runs_by_path(tmp_path: Path) -> None:
    file = _write(tmp_path / "tools" / "script.py", "")
    assert resolve(file, tmp_path / "src") == Target(path=file.resolve(), module=None)


def test_a_file_directly_in_src_runs_by_path(tmp_path: Path) -> None:
    file = _write(tmp_path / "src" / "loose.py", "")
    assert resolve(file, tmp_path / "src").module is None


def test_a_relative_path_is_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "src" / "pkg" / "cli.py", "")
    monkeypatch.chdir(tmp_path)
    assert resolve(Path("src") / "pkg" / "cli.py", tmp_path / "src").module == "pkg.cli"


@pytest.mark.usefixtures("isolated_sys")
def test_runs_a_package_module_as_main(tmp_path: Path) -> None:
    file = _write(tmp_path / "src" / "pkg" / "cli.py", "")
    calls: list[tuple[str, dict[str, Any]]] = []
    record = functools.partial(_recording_run, calls)
    code = main([str(file), "--help"], src=tmp_path / "src", run_module=record, run_path=record)
    assert code == 0
    assert calls == [("pkg.cli", {"run_name": "__main__", "alter_sys": True})]
    assert sys.argv == [str(file.resolve()), "--help"]


@pytest.mark.usefixtures("isolated_sys")
def test_falls_back_to_the_path_outside_src(tmp_path: Path) -> None:
    file = _write(tmp_path / "scripts" / "adhoc.py", "")
    calls: list[tuple[str, dict[str, Any]]] = []
    record = functools.partial(_recording_run, calls)
    main([str(file)], src=tmp_path / "src", run_module=record, run_path=record)
    assert calls == [(str(file.resolve()), {"run_name": "__main__"})]
    assert sys.path[0] == str(file.resolve().parent)


def test_no_arguments_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == USAGE
    assert "pass the file to run" in capsys.readouterr().err


def test_a_missing_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "absent.py")], src=tmp_path / "src") == USAGE
    assert "no such file" in capsys.readouterr().err


@pytest.mark.usefixtures("isolated_sys")
def test_a_package_module_keeps_its_relative_imports(fixture_package: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    entry = fixture_package / FIXTURE_PACKAGE / "cli.py"
    assert main([str(entry), str(out)], src=fixture_package) == 0
    assert out.read_text(encoding="utf-8") == "from a relative import"


@pytest.mark.usefixtures("isolated_sys")
def test_a_script_runs_as_main_and_imports_its_siblings(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    _write(tmp_path / "scripts" / "debug_module_sibling.py", "VALUE = 'sibling'\n")
    script = _write(
        tmp_path / "scripts" / "adhoc.py",
        "import sys\n"
        "from pathlib import Path\n"
        "from debug_module_sibling import VALUE\n"
        "Path(sys.argv[1]).write_text(f'{__name__} {VALUE}', encoding='utf-8')\n",
    )
    try:
        assert main([str(script), str(out)], src=tmp_path / "src") == 0
    finally:
        sys.modules.pop("debug_module_sibling", None)
    assert out.read_text(encoding="utf-8") == "__main__ sibling"


@pytest.mark.usefixtures("isolated_sys")
def test_the_target_exit_code_propagates(tmp_path: Path) -> None:
    script = _write(tmp_path / "exits.py", "import sys\nsys.exit(3)\n")
    with pytest.raises(SystemExit) as exited:
        main([str(script)], src=tmp_path / "src")
    assert exited.value.code == 3
