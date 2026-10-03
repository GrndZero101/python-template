"""Check the conventions in CLAUDE.md that no linter in the Astral stack covers.

Ruff, ty and pylint between them have no rule for a `def` or `class` inside a function, a
comprehension with two `for` clauses, `raise ... from None`, `getattr` with a computed name, a
`main` that cannot be run, an exit that drops the exception it caught, or an HTTP client built, or
patched, anywhere but its factory. These are the rules CLAUDE.md states and a weaker model forgets,
so they are checked rather than trusted. The rules themselves, their ids and the opt-out comment are in
`convention_rules.py`.

Usage:
    python tools/check_conventions.py src tests      # directories are expanded
    python tools/check_conventions.py a.py b.py      # or explicit files (how prek calls it)

Exits 1 when findings exist, 0 when clean, 2 on usage error.
"""

import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from convention_rules import Finding, check_source


def iter_python_files(paths: Iterable[str]) -> Iterator[Path]:
    """Yield .py files, expanding any directory among `paths` recursively."""
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.suffix == ".py" and path.is_file():
            yield path


def check_file(path: Path) -> list[Finding]:
    """Return the convention findings for a single file."""
    return check_source(path, path.read_text(encoding="utf-8"))


def _location(finding: Finding) -> str:
    """Return `path:line: rule:`, followed by what is particular to this finding, if anything."""
    head = f"{finding.path}:{finding.line}: {finding.rule}:"
    return f"{head} {finding.detail}" if finding.detail else head


def format_finding(finding: Finding) -> str:
    """Render a finding as its location, rule id and a message that states the fix."""
    return (
        f"{_location(finding)} {finding.message}\n"
        f"  If it is genuinely needed, add `# noqa: {finding.rule}` to that line and say why."
    )


def format_findings(findings: list[Finding]) -> list[str]:
    """Render each finding, giving a message already shown only its location.

    One habit — patching httpx in every test, say — can trip a rule twenty times, and the agent
    reads the whole report: the twentieth copy of a message costs tokens and says nothing new.
    """
    shown: set[tuple[str, str]] = set()
    rendered: list[str] = []
    for finding in findings:
        key = (finding.rule, finding.message)
        if key in shown:
            rendered.append(f"{_location(finding)} (fix as above)")
            continue
        shown.add(key)
        rendered.append(format_finding(finding))
    return rendered


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: check_conventions.py <file-or-directory>...", file=sys.stderr)
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
    print(f"Found {count} convention violation{plural}.\n", file=sys.stderr)
    for line in format_findings(findings):
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
