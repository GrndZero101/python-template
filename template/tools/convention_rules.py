"""The rules behind `check_conventions.py`: CLAUDE.md conventions that no Astral linter checks.

Each rule is a function from a parsed module to `Hit`s, and each hit's message names the fix, not
just the violation. A line opts out of one rule with `# noqa: <rule-id>` — several ids may be
listed, separated by commas — and the comment beside it should say why.

| Rule id | Flags |
|---|---|
| `nested-def` | a `def` inside a function, unless that function returns it |
| `nested-class` | a `class` inside a function |
| `complex-comprehension` | a comprehension with more than one `for`, or one inside another |
| `raise-from-none` | `raise ... from None` |
| `dynamic-attribute` | `getattr`, `setattr` or `delattr` with a computed attribute name |
| `missing-main-guard` | a module that defines `main` with no `if __name__ == "__main__":` |
"""

import ast
import dataclasses
import re
from collections.abc import Callable
from pathlib import Path

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
DYNAMIC_ATTRIBUTE_CALLS = frozenset({"getattr", "setattr", "delattr"})
ATTRIBUTE_NAME_ARG = 1  # getattr(obj, name, ...): the name is the second positional argument
NOQA_MARK = "# noqa:"
NOQA_SEPARATORS = re.compile(r"[,\s]+")


@dataclasses.dataclass(frozen=True)
class Hit:
    """One rule violation in a module, before it is tied to a file."""

    line: int
    rule: str
    message: str


@dataclasses.dataclass(frozen=True)
class Finding:
    """One rule violation in a file."""

    path: Path
    line: int
    rule: str
    message: str


def _returned_names(func: FunctionNode) -> set[str]:
    """Names the function returns directly, e.g. `return wrapper`.

    These are the decorator and factory patterns, where a nested def is the point.
    """
    returned: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            returned.add(node.value.id)
    return returned


def _nested_def_hit(child: FunctionNode, enclosing: FunctionNode) -> Hit | None:
    """Return a hit for `child` unless `enclosing` returns it."""
    if child.name in _returned_names(enclosing):
        return None
    message = (
        f"`{child.name}` is defined inside `{enclosing.name}`. Move it to module level and pass "
        "what it needs as arguments: a nested def cannot be breakpointed by name or called from "
        "pdb, and its closure is invisible in the debugger. If the closure is the point, return "
        f"it from `{enclosing.name}` (the decorator or factory pattern)."
    )
    return Hit(child.lineno, "nested-def", message)


def _nested_class_hit(child: ast.ClassDef, enclosing: FunctionNode) -> Hit:
    """Return the hit for a class defined inside a function."""
    message = (
        f"class `{child.name}` is defined inside `{enclosing.name}`. Move it to module level: a "
        "class built per call is a new type each time, which breaks `isinstance` and pickling."
    )
    return Hit(child.lineno, "nested-class", message)


class _ScopeScanner:
    """Walks a module tracking the nearest enclosing function, for the two scope rules.

    Deliberately not `ast.walk`: that would report a triply-nested def once per ancestor instead
    of once against its immediate parent.
    """

    def __init__(self) -> None:
        self.hits: list[Hit] = []

    def walk(self, node: ast.AST, enclosing: FunctionNode | None) -> None:
        """Recurse into `node`, recording definitions nested inside `enclosing`."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, FunctionNode):
                self._record_def(child, enclosing)
                self.walk(child, child)
            elif isinstance(child, ast.ClassDef):
                if enclosing is not None:
                    self.hits.append(_nested_class_hit(child, enclosing))
                # A method is not a nested function: reset the enclosing scope.
                self.walk(child, None)
            else:
                self.walk(child, enclosing)

    def _record_def(self, child: FunctionNode, enclosing: FunctionNode | None) -> None:
        """Record `child` if it is a nested def that is not returned."""
        if enclosing is None:
            return
        hit = _nested_def_hit(child, enclosing)
        if hit is not None:
            self.hits.append(hit)


def scope_hits(tree: ast.Module) -> list[Hit]:
    """Return `nested-def` and `nested-class` hits."""
    scanner = _ScopeScanner()
    scanner.walk(tree, None)
    return scanner.hits


def _comprehension_problem(node: ast.AST) -> str | None:
    """Describe what makes `node` too complex to inspect, or None if it is fine."""
    if not isinstance(node, COMPREHENSIONS):
        return None
    if len(node.generators) > 1:
        return f"comprehension with {len(node.generators)} `for` clauses"
    for inner in ast.walk(node):
        if inner is not node and isinstance(inner, COMPREHENSIONS):
            return "comprehension containing another comprehension"
    return None


def comprehension_hits(tree: ast.Module) -> list[Hit]:
    """Return `complex-comprehension` hits, reporting only the outermost of a nested set."""
    hits: list[Hit] = []
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        problem = _comprehension_problem(node)
        if problem is None:
            pending.extend(ast.iter_child_nodes(node))
            continue
        message = (
            f"{problem}. Write an explicit loop with named intermediates, so a breakpoint inside "
            "it has values to inspect."
        )
        hits.append(Hit(getattr(node, "lineno", 0), "complex-comprehension", message))
    return hits


def raise_hits(tree: ast.Module) -> list[Hit]:
    """Return `raise-from-none` hits."""
    message = (
        "`raise ... from None` discards the exception that caused this one. Bind it with "
        "`except SomeError as exc` and `raise ... from exc`: its traceback says where it started."
    )
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        if isinstance(node.cause, ast.Constant) and node.cause.value is None:
            hits.append(Hit(node.lineno, "raise-from-none", message))
    return hits


def _dynamic_attribute_call(node: ast.AST) -> str | None:
    """Return the builtin's name if `node` calls it with a computed attribute name."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None
    if node.func.id not in DYNAMIC_ATTRIBUTE_CALLS or len(node.args) <= ATTRIBUTE_NAME_ARG:
        return None
    name = node.args[ATTRIBUTE_NAME_ARG]
    if isinstance(name, ast.Constant) and isinstance(name.value, str):
        return None
    return node.func.id


def attribute_hits(tree: ast.Module) -> list[Hit]:
    """Return `dynamic-attribute` hits."""
    hits: list[Hit] = []
    for node in ast.walk(tree):
        builtin = _dynamic_attribute_call(node)
        if builtin is None:
            continue
        message = (
            f"`{builtin}` with a computed attribute name. Name the attribute in the code, or "
            "dispatch through an explicit dict of functions: grep and breakpoints cannot follow "
            "a name built at runtime."
        )
        hits.append(Hit(getattr(node, "lineno", 0), "dynamic-attribute", message))
    return hits


def _is_main_guard(node: ast.stmt) -> bool:
    """Return whether `node` is `if __name__ == "__main__":`, written either way round."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    operands = [node.test.left, *node.test.comparators]
    names = {operand.id for operand in operands if isinstance(operand, ast.Name)}
    values = {operand.value for operand in operands if isinstance(operand, ast.Constant)}
    return names == {"__name__"} and values == {"__main__"}


def main_guard_hits(tree: ast.Module) -> list[Hit]:
    """Return a `missing-main-guard` hit if the module defines `main` but cannot run it."""
    main_def = None
    for node in tree.body:
        if isinstance(node, FunctionNode) and node.name == "main":
            main_def = node
    if main_def is None or any(_is_main_guard(node) for node in tree.body):
        return []
    message = (
        'this module defines `main` but has no `if __name__ == "__main__":` block. Add one at '
        "the bottom calling `sys.exit(main())`, so the module runs standalone and under a debugger."
    )
    return [Hit(main_def.lineno, "missing-main-guard", message)]


RULES: tuple[Callable[[ast.Module], list[Hit]], ...] = (
    scope_hits,
    comprehension_hits,
    raise_hits,
    attribute_hits,
    main_guard_hits,
)


def suppressed(line: str, rule: str) -> bool:
    """Return whether `line` carries `# noqa:` naming `rule`."""
    start = line.find(NOQA_MARK)
    if start == -1:
        return False
    named = NOQA_SEPARATORS.split(line[start + len(NOQA_MARK) :])
    return rule in named


def check_source(path: Path, source: str) -> list[Finding]:
    """Return every unsuppressed finding in `source`, in line order."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # ruff already reports syntax errors; don't double-report
    lines = source.splitlines()
    findings: list[Finding] = []
    for rule in RULES:
        for hit in rule(tree):
            text = lines[hit.line - 1] if 0 < hit.line <= len(lines) else ""
            if not suppressed(text, hit.rule):
                findings.append(Finding(path, hit.line, hit.rule, hit.message))
    return sorted(findings, key=_line_order)


def _line_order(finding: Finding) -> tuple[int, str]:
    """Sort key: by line, then by rule id."""
    return (finding.line, finding.rule)
