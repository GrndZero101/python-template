"""Run pytest as a plain script, so a debugger that can only launch a `program` can debug tests.

The standalone DebugMCP CLI always sets debugpy's `program` to a file, which rules out the
`"module": "pytest"` launch the VS Code configurations use: debugpy refuses a launch that names
both. The `pytest` adapter in `.debugmcp.json` points `program` here instead and passes the test
file through as an argument.
"""

import sys
from collections.abc import Callable, Sequence

import pytest

PytestMain = Callable[[list[str]], int]


def main(argv: Sequence[str] | None = None, run: PytestMain = pytest.main) -> int:
    """Run pytest with `argv`, defaulting to this process's arguments, and return its exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    return int(run(args))


if __name__ == "__main__":
    sys.exit(main())
