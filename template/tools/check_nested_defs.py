"""Flag function definitions nested inside other functions.

No linter in the Astral stack has a rule for `def` inside `def`. Ruff's nesting rules
(PLR1702, E306, D106, F406, PLW3301, RUF041) all cover something else, and neither pylint
nor ty has one. This is the single gap that justifies custom code in this project.

A nested `def` is flagged unless the enclosing function *returns* it, which is what makes
decorators and factories legitimate. Per-line opt-out: `# noqa: nested-def`.

Usage:
    python tools/check_nested_defs.py src tests      # directories are expanded
    python tools/check_nested_defs.py a.py b.py      # or explicit files (how prek calls it)

Exits 1 when findings exist, 0 when clean, 2 on usage error.
"""

import ast
import dataclasses
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
SUPPRESSION = "# noqa: nested-def"


@dataclasses.dataclass(frozen=True)
class Finding:
    """One function defined inside another function."""

    path: Path
    line: int
    inner: str
    outer: str


def _returned_names(func: FunctionNode) -> set[str]:
    """Names the function returns directly, e.g. `return wrapper`.

    These are the decorator and factory patterns, where a nested def is the point.
    """
    return {
        node.value.id
        for node in ast.walk(func)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
    }


class _Scanner:
    """Walks a module tracking the nearest enclosing function.

    Deliberately not `ast.walk`: that would report a triply-nested def once per
    ancestor instead of once against its immediate parent.
    """

    def __init__(self, path: Path, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.findings: list[Finding] = []

    def walk(self, node: ast.AST, enclosing: FunctionNode | None) -> None:
        """Recurse into `node`, recording any function nested inside `enclosing`."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, FunctionNode):
                self._record(child, enclosing)
                self.walk(child, child)
            elif isinstance(child, ast.ClassDef):
                # A method is not a nested function: reset the enclosing scope.
                self.walk(child, None)
            else:
                self.walk(child, enclosing)

    def _record(self, child: FunctionNode, enclosing: FunctionNode | None) -> None:
        if enclosing is None:
            return
        if child.name in _returned_names(enclosing):
            return
        if SUPPRESSION in self.lines[child.lineno - 1]:
            return
        self.findings.append(
            Finding(path=self.path, line=child.lineno, inner=child.name, outer=enclosing.name)
        )


def iter_python_files(paths: Iterable[str]) -> Iterator[Path]:
    """Yield .py files, expanding any directory among `paths` recursively."""
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.suffix == ".py" and path.is_file():
            yield path


def check_file(path: Path) -> list[Finding]:
    """Return the nested-definition findings for a single file."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # ruff already reports syntax errors; don't double-report
    scanner = _Scanner(path, source.splitlines())
    scanner.walk(tree, None)
    return scanner.findings


def format_finding(finding: Finding) -> str:
    """Render a finding as a message that states the fix, not just the violation."""
    return (
        f"{finding.path}:{finding.line}  `{finding.inner}` is nested inside `{finding.outer}`.\n"
        f"  Move it to module level and pass what it needs explicitly. Nested defs cannot be\n"
        f"  breakpointed by name or called from pdb, and their closure state is invisible in\n"
        f"  the debugger. If the closure is genuinely the point, return it from "
        f"`{finding.outer}`\n"
        f"  (the decorator/factory pattern) or add `{SUPPRESSION}` to its `def` line."
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: check_nested_defs.py <file-or-directory>...", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    for path in iter_python_files(args):
        findings.extend(check_file(path))

    if not findings:
        return 0

    # Everything goes to stderr: on a blocking exit the Claude Code hook discards
    # stdout entirely and feeds only stderr back as the error to act on.
    count = len(findings)
    plural = "" if count == 1 else "s"
    print(f"Found {count} nested function definition{plural}.\n", file=sys.stderr)
    for finding in findings:
        print(format_finding(finding), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
