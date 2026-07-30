"""Run a typer app and return an exit code instead of calling sys.exit.

typer 0.27 no longer depends on the `click` package — it vendors its own fork
at `typer._click`, so the exception types this needs are not part of typer's
public API. This module isolates that one private import so it exists in a
single place if a future typer release changes it.
"""

import typer
from typer._click.exceptions import (  # ruff: ignore[import-private-name]
    ClickException,
    NoArgsIsHelpError,
)


def run_app(app: typer.Typer, argv: list[str] | None, prog_name: str) -> int:
    """Invoke `app` with `argv` and translate its result into an exit code.

    With `standalone_mode=False`, typer's own dispatch (`typer/core.py::_main`)
    already catches an internally raised `typer.Exit` and *returns* its exit
    code rather than re-raising it — the exit code never reaches this frame
    as an exception. Only a genuine usage error (`ClickException`, e.g. an
    unknown flag) still propagates as one.

    A bare invocation of a `no_args_is_help=True` app raises `NoArgsIsHelpError`
    (a `ClickException` with exit_code 2) after printing help — that is a
    request for help, not a usage error, so it is translated to exit code 0.
    """
    try:
        result = app(args=argv, standalone_mode=False, prog_name=prog_name)
    except NoArgsIsHelpError as exc:
        exc.show()
        return 0
    except ClickException as exc:
        exc.show()
        return int(exc.exit_code)
    return int(result) if isinstance(result, int) else 0
