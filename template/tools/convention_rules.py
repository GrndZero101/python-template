"""The rules behind `check_conventions.py`: CLAUDE.md conventions that no Astral linter checks.

Each rule is a function from a parsed module to `Hit`s, and each hit's message names the fix, not
just the violation. What is particular to one hit — the names involved — goes in its `detail`, so
the advice itself is identical across hits and the report can print it once. A line opts out of one rule with `# noqa: <rule-id>` — several ids may be
listed, separated by commas — and the comment beside it should say why.

| Rule id | Flags |
|---|---|
| `nested-def` | a `def` inside a function, unless that function returns it |
| `nested-class` | a `class` inside a function |
| `complex-comprehension` | a comprehension with more than one `for`, or one inside another |
| `raise-from-none` | `raise ... from None` |
| `dynamic-attribute` | `getattr`, `setattr` or `delattr` with a computed attribute name |
| `missing-main-guard` | a module that defines `main` with no `if __name__ == "__main__":` |
| `raw-httpx-client` | an httpx client, or an `httpx.get`-style call, built outside `build_client` |
| `patched-httpx` | `patch`, `patch.object` or `setattr` aimed at httpx itself |
| `silent-exit` | an exit raised from an `except` that never reports the exception it caught |
"""

import ast
import dataclasses
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeGuard

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
DYNAMIC_ATTRIBUTE_CALLS = frozenset({"getattr", "setattr", "delattr"})
ATTRIBUTE_NAME_ARG = 1  # getattr(obj, name, ...): the name is the second positional argument
NOQA_MARK = "# noqa:"
NOQA_SEPARATORS = re.compile(r"[,\s]+")
HTTPX_CLIENTS = frozenset({"Client", "AsyncClient"})
# httpx's module-level shortcuts, each of which builds a throwaway client with the defaults.
HTTPX_SHORTCUTS = frozenset({
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "request",
    "stream",
})
CLIENT_FACTORY = "build_client"
PATCHERS = frozenset({"patch", "object", "setattr"})
EXIT_EXCEPTIONS = frozenset({"Exit", "Abort", "SystemExit"})


@dataclasses.dataclass(frozen=True)
class Hit:
    """One rule violation in a module, before it is tied to a file."""

    line: int
    rule: str
    message: str
    detail: str = ""


@dataclasses.dataclass(frozen=True)
class Finding:
    """One rule violation in a file."""

    path: Path
    line: int
    rule: str
    message: str
    detail: str = ""


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
        "Move it to module level and pass what it needs as arguments; where it is handed over as "
        "a callback, bind those arguments with `functools.partial(helper, value)`. A nested def "
        "cannot be breakpointed by name or called from pdb, and its closure is invisible in the "
        "debugger. Return a nested def only from a decorator or factory whose whole job is the "
        "closure; a test handler is neither."
    )
    detail = f"`{child.name}` is defined inside `{enclosing.name}`."
    return Hit(child.lineno, "nested-def", message, detail)


def _nested_class_hit(child: ast.ClassDef, enclosing: FunctionNode) -> Hit:
    """Return the hit for a class defined inside a function."""
    message = (
        "Move it to module level: a class built per call is a new type each time, which breaks "
        "`isinstance` and pickling."
    )
    detail = f"class `{child.name}` is defined inside `{enclosing.name}`."
    return Hit(child.lineno, "nested-class", message, detail)


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
            "Write an explicit loop with named intermediates, so a breakpoint inside it has "
            "values to inspect."
        )
        line = getattr(node, "lineno", 0)
        hits.append(Hit(line, "complex-comprehension", message, f"{problem}."))
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
            "Name the attribute in the code, or dispatch through an explicit dict of functions: "
            "grep and breakpoints cannot follow a name built at runtime."
        )
        detail = f"`{builtin}` with a computed attribute name."
        hits.append(Hit(getattr(node, "lineno", 0), "dynamic-attribute", message, detail))
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


@dataclasses.dataclass(frozen=True)
class HttpxNames:
    """How a module refers to httpx: the names bound to the module, and to its members."""

    modules: frozenset[str]
    members: dict[str, str]  # local name -> the httpx attribute it was imported as


def httpx_names(tree: ast.Module) -> HttpxNames:
    """Collect `import httpx [as h]` and `from httpx import Client [as C]` bindings."""
    modules: set[str] = set()
    members: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases = [alias for alias in node.names if alias.name == "httpx"]
            modules.update(alias.asname or "httpx" for alias in aliases)
        elif isinstance(node, ast.ImportFrom) and node.module == "httpx":
            members.update({alias.asname or alias.name: alias.name for alias in node.names})
    return HttpxNames(frozenset(modules), members)


def _httpx_attribute(node: ast.expr, names: HttpxNames) -> str | None:
    """Return the httpx attribute `node` names, as `httpx.Client` or an imported `Client`."""
    if isinstance(node, ast.Name):
        return names.members.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.attr if node.value.id in names.modules else None
    return None


def _rooted_in_httpx(node: ast.expr, names: HttpxNames) -> bool:
    """Return whether `node` is httpx or something reached from it, e.g. `httpx.Client.get`."""
    root = node
    while isinstance(root, ast.Attribute):
        root = root.value
    if not isinstance(root, ast.Name):
        return False
    return root.id in names.modules or root.id in names.members


def _calls_outside(tree: ast.Module, factory: str) -> Iterator[ast.Call]:
    """Yield every call in `tree` that is not inside a function named `factory`."""
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, FunctionNode) and node.name == factory:
            continue
        if isinstance(node, ast.Call):
            yield node
        pending.extend(ast.iter_child_nodes(node))


def _real_client(call: ast.Call, names: HttpxNames) -> str | None:
    """Return what `call` builds if it is an httpx client that would reach the network.

    A client given `transport=` is a test double — `MockTransport`, `ASGITransport` — so it
    passes, as does one given `**kwargs`, where the transport cannot be seen.
    """
    attribute = _httpx_attribute(call.func, names)
    if attribute in HTTPX_SHORTCUTS:
        return f"httpx.{attribute}()"
    if attribute not in HTTPX_CLIENTS:
        return None
    keywords = {keyword.arg for keyword in call.keywords}
    if "transport" in keywords or None in keywords:
        return None
    return f"httpx.{attribute}()"


def client_hits(tree: ast.Module) -> list[Hit]:
    """Return `raw-httpx-client` hits: clients built anywhere but `build_client`."""
    names = httpx_names(tree)
    if not names.modules and not names.members:
        return []
    hits: list[Hit] = []
    for call in _calls_outside(tree, CLIENT_FACTORY):
        built = _real_client(call, names)
        if built is None:
            continue
        message = (
            f"`{built}` builds a client with no retries, no User-Agent and default timeouts. "
            f"Call `{CLIENT_FACTORY}()` from `http_client.py` in the command, and pass the client "
            "down. No `http_client.py` yet? Copy it and its test from "
            "`.claude/skills/python-cli-modern/reference/` — the python-cli-modern skill, "
            '"Recipe: call an HTTP API".'
        )
        hits.append(Hit(call.lineno, "raw-httpx-client", message))
    return hits


def _called_name(func: ast.expr) -> str | None:
    """Return the last name in `func`: `patch`, `object` in `mock.patch.object`, `Exit`."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _patches_httpx(call: ast.Call, names: HttpxNames) -> bool:
    """Return whether `call` patches httpx itself, by object or by dotted string."""
    if _called_name(call.func) not in PATCHERS or not call.args:
        return False
    target = call.args[0]
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return target.value.split(".")[0] == "httpx"
    return _rooted_in_httpx(target, names)


def patch_hits(tree: ast.Module) -> list[Hit]:
    """Return `patched-httpx` hits."""
    names = httpx_names(tree)
    message = (
        "this patches httpx itself, for every caller at once, and hides what the code under test "
        "sends. Give it a client built with `transport=httpx.MockTransport(handler)` instead: "
        "pass one to the function, or replace the command module's `build_client` for a test "
        "through `main`. `.claude/skills/python-cli-modern/reference/test_status.py` shows both."
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    patches = [call for call in calls if _patches_httpx(call, names)]
    return [Hit(call.lineno, "patched-httpx", message) for call in patches]


def _raises_exit(node: ast.AST) -> TypeGuard[ast.Raise]:
    """Return whether `node` raises `typer.Exit`, `typer.Abort` or `SystemExit`."""
    if not isinstance(node, ast.Raise) or node.exc is None:
        return False
    raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    return _called_name(raised) in EXIT_EXCEPTIONS


def _reports(handler: ast.ExceptHandler) -> bool:
    """Return whether the handler passes on the exception it caught, whole.

    `f"{exc}"`, `str(exc)` and `logger.opt(exception=exc)` count; `from exc` does not, since
    nothing prints an exit's cause, and nor does `exc.request`, which reports a part and drops
    the reason.
    """
    if handler.name is None:
        return False
    hidden: set[int] = set()  # ids of uses that do not carry the exception anywhere visible
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and node.cause is not None:
            hidden.add(id(node.cause))
        elif isinstance(node, ast.Attribute):
            hidden.add(id(node.value))
    for node in ast.walk(handler):
        if isinstance(node, ast.Name) and node.id == handler.name and id(node) not in hidden:
            return True
    return False


def _is_interrupt(handler: ast.ExceptHandler) -> bool:
    """Return whether the handler catches only Ctrl-C, whose cause the user already knows."""
    return isinstance(handler.type, ast.Name) and handler.type.id == "KeyboardInterrupt"


def exit_hits(tree: ast.Module) -> list[Hit]:
    """Return `silent-exit` hits: an exit from an `except` that drops what it caught."""
    hits: list[Hit] = []
    reported: set[int] = set()  # a raise inside nested handlers is reported once, by the outer
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or _is_interrupt(handler):
            continue
        if _reports(handler):
            continue
        message = (
            "This exit drops the exception it caught: typer never prints an exit's cause, so the "
            "user sees no reason and `-v` shows nothing. Bind it (`except ... as exc`), put the "
            "whole of it in the stderr message (`{exc}`) and log it with "
            '`logger.opt(exception=exc).debug("...")` before exiting.'
        )
        exits = [node for node in ast.walk(handler) if _raises_exit(node)]
        for exit_raise in exits:
            if id(exit_raise) not in reported:
                reported.add(id(exit_raise))
                hits.append(Hit(exit_raise.lineno, "silent-exit", message))
    return hits


RULES: tuple[Callable[[ast.Module], list[Hit]], ...] = (
    scope_hits,
    comprehension_hits,
    raise_hits,
    attribute_hits,
    main_guard_hits,
    client_hits,
    patch_hits,
    exit_hits,
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
                findings.append(Finding(path, hit.line, hit.rule, hit.message, hit.detail))
    return sorted(findings, key=_line_order)


def _line_order(finding: Finding) -> tuple[int, str]:
    """Sort key: by line, then by rule id."""
    return (finding.line, finding.rule)
