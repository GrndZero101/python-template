"""Cases the nested-def checker must get right.

The exemption cases matter as much as the violation cases: a checker that misfires on
legitimate decorators and factories gets disabled, and then it protects nothing.
"""

from pathlib import Path

import pytest
from check_nested_defs import check_file, main

VIOLATIONS = {
    "plain helper": """
        def outer(a):
            def _helper(b):
                return b * 2
            return _helper(a)
    """,
    "method helper": """
        class C:
            def method(self):
                def _nested():
                    return 2
                return _nested()
    """,
    "async": """
        async def outer():
            async def _inner():
                return 1
            return await _inner()
    """,
    "not returned, merely called": """
        def outer():
            def _cb():
                return 1
            return [_cb() for _ in range(3)]
    """,
}

EXEMPTIONS = {
    "decorator returning wrapper": """
        import functools

        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)
            return wrapper
    """,
    "factory returning inner": """
        def factory():
            def inner():
                return 1
            return inner
    """,
    "returned on one branch only": """
        def cond(flag):
            def _a():
                return 1
            if flag:
                return _a
            return None
    """,
    "noqa suppression": """
        def outer():
            def _cb():  # noqa: nested-def
                return 3
            return _cb()
    """,
    "module-level siblings": """
        def _helper(b):
            return b * 2

        def outer(a):
            return _helper(a)
    """,
    "methods in a class are not nested": """
        class C:
            def a(self):
                return 1

            def b(self):
                return 2
    """,
}


def write_module(tmp_path: Path, source: str) -> Path:
    """Write dedented source to a temp .py file and return its path."""
    path = tmp_path / "sample.py"
    path.write_text(dedent_block(source), encoding="utf-8")
    return path


def dedent_block(source: str) -> str:
    """Strip the uniform leading indentation used by the fixtures above."""
    lines = source.strip("\n").splitlines()
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    pad = min(indents)
    return "\n".join(line[pad:] if line.strip() else "" for line in lines) + "\n"


@pytest.mark.parametrize("source", VIOLATIONS.values(), ids=list(VIOLATIONS))
def test_flags_nested_definitions(tmp_path: Path, source: str) -> None:
    assert check_file(write_module(tmp_path, source))


@pytest.mark.parametrize("source", EXEMPTIONS.values(), ids=list(EXEMPTIONS))
def test_allows_legitimate_definitions(tmp_path: Path, source: str) -> None:
    assert check_file(write_module(tmp_path, source)) == []


def test_reports_immediate_parent_once(tmp_path: Path) -> None:
    """A triply-nested def is reported once, against its immediate parent.

    This is why the scanner uses recursive descent rather than ast.walk.
    """
    source = """
        def outer(a):
            def _helper(b):
                def _deeper(c):
                    return c
                return _deeper(b)
            return _helper(a)
    """
    findings = check_file(write_module(tmp_path, source))
    assert [(f.inner, f.outer) for f in findings] == [
        ("_helper", "outer"),
        ("_deeper", "_helper"),
    ]


def test_syntax_errors_are_left_to_ruff(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def (:\n", encoding="utf-8")
    assert check_file(path) == []


def test_main_returns_exit_codes(tmp_path: Path) -> None:
    clean = write_module(tmp_path, "def f():\n    return 1\n")
    assert main([str(clean)]) == 0
    assert main([str(write_module(tmp_path, VIOLATIONS["plain helper"]))]) == 1
    assert main([]) == 2


def test_directories_are_expanded(tmp_path: Path) -> None:
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "bad.py").write_text(
        dedent_block(VIOLATIONS["plain helper"]),
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 1
