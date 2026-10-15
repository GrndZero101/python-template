"""Run a typer app and return an exit code instead of calling sys.exit.

typer 0.27 no longer depends on the `click` package — it vendors its own fork
at `typer._click`, so the exception types this needs are not part of typer's
public API. This module isolates that one private import so it exists in a
single place if a future typer release changes it.
"""

import contextlib
import sys

import typer
from typer._click.exceptions import (  # ruff: ignore[import-private-name]
    ClickException,
    MissingParameter,
    NoArgsIsHelpError,
)


def _show_help_for_missing(exc: MissingParameter) -> None:
    """Print the command's full help, then the error, both to stderr.

    With rich installed, typer's help formatter prints straight to stdout and `get_help()`
    returns an empty string, so stdout is redirected around the call. rich looks `sys.stdout`
    up at write time, so the redirect catches it; the plain formatter returns its text instead,
    which is echoed to stderr explicitly.
    """
    if exc.ctx is None:
        exc.show()
        return
    with contextlib.redirect_stdout(sys.stderr):
        help_text = exc.ctx.get_help()
    if help_text:
        typer.echo(help_text, err=True, color=exc.ctx.color)
    typer.echo(f"Error: {exc.format_message()}", err=True, color=exc.ctx.color)


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

    A command missing a required argument raises `MissingParameter`, whose own
    `.show()` prints only a terse usage line. The full help is more useful, so it
    is printed instead, followed by the error. It is still a usage error, though:
    the exit code stays 2 and everything goes to stderr, so `tool cmd && next`
    stops and nothing lands in a pipe.
    """
    try:
        result = app(args=argv, standalone_mode=False, prog_name=prog_name)
    except NoArgsIsHelpError as exc:
        exc.show()
        return 0
    except MissingParameter as exc:
        _show_help_for_missing(exc)
        return int(exc.exit_code)
    except ClickException as exc:
        exc.show()
        return int(exc.exit_code)
    return int(result) if isinstance(result, int) else 0
