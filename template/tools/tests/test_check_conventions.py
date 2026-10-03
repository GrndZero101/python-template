"""Cases the conventions checker must get right.

The exemption cases matter as much as the violation cases: a checker that misfires on
legitimate decorators and factories gets disabled, and then it protects nothing.
"""

from pathlib import Path

import pytest
from check_conventions import check_file, format_finding, format_findings, main
from convention_rules import suppressed

NESTED_DEFS = {
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

# Each case names the one rule it must trip.
VIOLATIONS = {
    **{name: ("nested-def", source) for name, source in NESTED_DEFS.items()},
    "class in a function": (
        "nested-class",
        """
        def build():
            class _Local:
                pass
            return _Local()
        """,
    ),
    "class in a method": (
        "nested-class",
        """
        class Outer:
            def make(self):
                class _Inner:
                    pass
                return _Inner
        """,
    ),
    "two for clauses": (
        "complex-comprehension",
        """
        pairs = [(a, b) for a in range(3) for b in range(3)]
        """,
    ),
    "comprehension in a comprehension": (
        "complex-comprehension",
        """
        grid = [[cell for cell in row] for row in [[1, 2], [3]]]
        """,
    ),
    "generator in a dict comprehension": (
        "complex-comprehension",
        """
        sizes = {key: sum(v for v in values) for key, values in {}.items()}
        """,
    ),
    "raise from None": (
        "raise-from-none",
        """
        def parse(text):
            try:
                return int(text)
            except ValueError:
                raise TypeError("not a number") from None
        """,
    ),
    "getattr with a variable name": (
        "dynamic-attribute",
        """
        def dispatch(obj, name):
            return getattr(obj, name)()
        """,
    ),
    "setattr with an f-string": (
        "dynamic-attribute",
        """
        def stamp(obj, field):
            setattr(obj, f"seen_{field}", True)
        """,
    ),
    "main without a guard": (
        "missing-main-guard",
        """
        def main(argv=None):
            return 0
        """,
    ),
    "a bare httpx client": (
        "raw-httpx-client",
        """
        import httpx

        def lookup(query, client=None):
            client = client or httpx.Client()
            return client.get("https://example.test/", params={"q": query})
        """,
    ),
    "an imported AsyncClient": (
        "raw-httpx-client",
        """
        from httpx import AsyncClient as Http

        async def fetch():
            async with Http(timeout=5) as client:
                return await client.get("https://example.test/")
        """,
    ),
    "an httpx shortcut": (
        "raw-httpx-client",
        """
        import httpx

        def status():
            return httpx.get("https://example.test/").status_code
        """,
    ),
    "patch.object on an httpx class": (
        "patched-httpx",
        """
        from unittest.mock import patch

        import httpx

        def test_it():
            with patch.object(httpx.Client, "get"):
                pass
        """,
    ),
    "patch by dotted string": (
        "patched-httpx",
        """
        from unittest import mock

        def test_it():
            with mock.patch("httpx.Client.send"):
                pass
        """,
    ),
    "monkeypatch.setattr on httpx": (
        "patched-httpx",
        """
        import httpx

        def test_it(monkeypatch):
            monkeypatch.setattr(httpx, "get", None)
        """,
    ),
    "exit whose cause is only chained": (
        "silent-exit",
        """
        import httpx
        import typer

        def command(client):
            try:
                client.get("https://example.test/")
            except httpx.HTTPError as exc:
                typer.echo("request failed", err=True)
                raise typer.Exit(1) from exc
        """,
    ),
    "exit that reports only a part of what it caught": (
        "silent-exit",
        """
        import httpx
        import typer

        def command(client):
            try:
                client.get("https://example.test/")
            except httpx.HTTPError as exc:
                typer.echo(f"request to {exc.request.url} failed", err=True)
                raise typer.Exit(1) from exc
        """,
    ),
    "exit from an unbound handler": (
        "silent-exit",
        """
        def command(path):
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                raise SystemExit(1)
        """,
    ),
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
    "class nested in a class": """
        class Outer:
            class Config:
                frozen = True
    """,
    "one for clause with a condition": """
        evens = [n for n in range(10) if n % 2 == 0]
    """,
    "comprehension beside a comprehension": """
        both = [n for n in range(3)] + [n for n in range(4)]
    """,
    "raise from the caught exception": """
        def parse(text):
            try:
                return int(text)
            except ValueError as exc:
                raise TypeError("not a number") from exc
    """,
    "getattr with a literal name and default": """
        def version(module):
            return getattr(module, "__version__", "unknown")
    """,
    "main with a guard": """
        import sys

        def main(argv=None):
            return 0

        if __name__ == "__main__":
            sys.exit(main())
    """,
    "main guard written the other way round": """
        def main():
            return 0

        if "__main__" == __name__:
            main()
    """,
    "a method called main is not a module main": """
        class App:
            def main(self):
                return 0
    """,
    "a client from the factory": """
        import httpx

        def build_client(transport=None):
            return httpx.Client(timeout=5)
    """,
    "a test double passes its transport": """
        import httpx

        def test_it(handler):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                assert client.get("https://example.test/").status_code == 200
    """,
    "a client whose keywords cannot be seen": """
        import httpx

        def make(**options):
            return httpx.Client(**options)
    """,
    "a get that is not httpx's": """
        import requests

        def status(session):
            return session.get("https://example.test/"), requests.get("https://example.test/")
    """,
    "patching the module's own factory": """
        def test_it(monkeypatch, status, factory):
            monkeypatch.setattr(status, "build_client", factory)
    """,
    "exit that reports what it caught": """
        import httpx
        import typer
        from loguru import logger

        def command(client):
            try:
                client.get("https://example.test/")
            except httpx.HTTPError as exc:
                logger.opt(exception=exc).debug("request failed")
                typer.echo(f"request failed: {exc}", err=True)
                raise typer.Exit(1) from exc
    """,
    "exit on Ctrl-C": """
        import typer

        def command(work):
            try:
                work()
            except KeyboardInterrupt:
                raise typer.Exit(130)
    """,
    "an exit outside any handler": """
        import typer

        def command(names):
            if not names:
                raise typer.Exit(2)
    """,
    "noqa naming several rules": """
        def parse(text):
            try:
                return int(text)
            except ValueError:
                raise TypeError("bad") from None  # noqa: dynamic-attribute, raise-from-none
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


@pytest.mark.parametrize(("rule", "source"), VIOLATIONS.values(), ids=list(VIOLATIONS))
def test_flags_each_violation_under_its_own_rule(tmp_path: Path, rule: str, source: str) -> None:
    findings = check_file(write_module(tmp_path, source))
    assert [finding.rule for finding in findings] == [rule]


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
    assert [(finding.line, finding.rule) for finding in findings] == [
        (2, "nested-def"),
        (3, "nested-def"),
    ]
    assert "inside `outer`" in findings[0].detail
    assert "inside `_helper`" in findings[1].detail


def test_reports_only_the_outermost_of_nested_comprehensions(tmp_path: Path) -> None:
    source = "cube = [[[z for z in range(2)] for y in range(2)] for x in range(2)]\n"
    findings = check_file(write_module(tmp_path, source))
    assert len(findings) == 1


def test_noqa_must_name_the_rule() -> None:
    """Silencing one rule must not silence another on the same line."""
    assert suppressed("x  # noqa: raise-from-none", "raise-from-none")
    assert suppressed("x  # noqa: nested-def,raise-from-none", "raise-from-none")
    assert not suppressed("x  # noqa: nested-def", "raise-from-none")
    assert not suppressed("x  # raise-from-none", "raise-from-none")


def test_message_names_location_rule_and_opt_out(tmp_path: Path) -> None:
    path = write_module(tmp_path, VIOLATIONS["raise from None"][1])
    rendered = format_finding(check_file(path)[0])
    assert rendered.startswith(f"{path}:5: raise-from-none: ")
    assert "from exc" in rendered
    assert "# noqa: raise-from-none" in rendered


def test_a_repeated_message_is_shown_once(tmp_path: Path) -> None:
    case = VIOLATIONS["patch.object on an httpx class"][1]
    path = write_module(tmp_path, case + case)
    rendered = format_findings(check_file(path))
    assert len(rendered) == 2
    assert "MockTransport" in rendered[0]
    assert rendered[1].endswith("patched-httpx: (fix as above)")


def test_repeated_advice_keeps_each_hits_names(tmp_path: Path) -> None:
    source = """
        def first():
            def _a():
                return 1
            return _a()

        def second():
            def _b():
                return 2
            return _b()
    """
    rendered = format_findings(check_file(write_module(tmp_path, source)))
    assert "functools.partial" in rendered[0]
    assert rendered[1].endswith("`_b` is defined inside `second`. (fix as above)")


def test_syntax_errors_are_left_to_ruff(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def (:\n", encoding="utf-8")
    assert check_file(path) == []


def test_main_returns_exit_codes(tmp_path: Path) -> None:
    clean = write_module(tmp_path, "def f():\n    return 1\n")
    assert main([str(clean)]) == 0
    assert main([str(write_module(tmp_path, NESTED_DEFS["plain helper"]))]) == 1
    assert main([]) == 2


def test_directories_are_expanded(tmp_path: Path) -> None:
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "bad.py").write_text(
        dedent_block(NESTED_DEFS["plain helper"]),
        encoding="utf-8",
    )
    assert main([str(tmp_path)]) == 1
