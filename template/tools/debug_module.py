"""Run a source file as `python -m` would, so a debugger that can only launch a `program` can run it.

The standalone DebugMCP CLI always sets debugpy's `program` to the requested file, which launches it
as a top-level script. Every module under `src/` uses relative imports, so the first one fails with
`ImportError: attempted relative import with no known parent package` — and because the debuggee's
output is not captured, the agent sees only "ran to completion". Nor can `"module"` fix it: debugpy
refuses a launch naming both `program` and `module`.

The `python` adapter in `.debugmcp.json` points `program` here instead and passes the requested file
as the first argument. A file inside a package under `src/` runs as its dotted module name; any
other file — a standalone script, something under `tools/`, an ad-hoc file anywhere — falls back to
running by path, as `python <file>` would.

It runs by hand too, which is how to see the output the debugger hides:

    uv run python tools/debug_module.py src/<package>/cli.py --help

A `SystemExit` raised by the target is deliberately not caught: it carries the target's exit code.
"""

import runpy
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
USAGE = 2

Runner = Callable[..., object]


@dataclass(frozen=True)
class Target:
    """What to run: `module` is the dotted name under `src/`, or None to run `path` directly."""

    path: Path
    module: str | None


def resolve(file: Path, src: Path = SRC_DIR) -> Target:
    """Map `file` to a dotted module name when it sits in a package under `src`.

    A file directly in `src/` belongs to no package, so it has no relative imports to protect and
    runs by path like any other script.
    """
    path = file.resolve()
    try:
        relative = path.relative_to(src.resolve())
    except ValueError:
        return Target(path=path, module=None)
    if relative.parent == Path():
        return Target(path=path, module=None)
    module = ".".join(relative.with_suffix("").parts)
    return Target(path=path, module=module)


def _point_sys_at(target: Target, args: Sequence[str]) -> None:
    """Make `sys.argv`, and for a script `sys.path[0]`, look as they would without the launcher."""
    sys.argv = [str(target.path), *args]
    if target.module is None:
        sys.path[0] = str(target.path.parent)


def main(
    argv: Sequence[str] | None = None,
    *,
    src: Path = SRC_DIR,
    run_module: Runner = runpy.run_module,
    run_path: Runner = runpy.run_path,
) -> int:
    """Run the file named first in `argv` as `__main__`, passing it the rest. Returns an exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: debug_module.py FILE [ARG ...]; pass the file to run first\n")
        return USAGE
    target = resolve(Path(args[0]), src)
    if not target.path.is_file():
        sys.stderr.write(f"no such file: {target.path}; pass the path of a Python file\n")
        return USAGE
    _point_sys_at(target, args[1:])
    if target.module is None:
        run_path(str(target.path), run_name="__main__")
    else:
        run_module(target.module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
