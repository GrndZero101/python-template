"""Single entry point mounting every subcommand.

    cli geo cleve
    cli currency 1000 GBP/AUD --margin 2.5

Each subcommand lives in its own module and is registered here as a plain function, not with
its own nested `typer.Typer`. Registration by reference keeps `cli geo …` two words instead of
three, and keeps `geo` importable and callable on its own — from a test, from pdb, or from a
debugger's evaluate-expression prompt with literal arguments.

`add_completion=False` is deliberate. Typer's `--install-completion` rewrites `~/.zshrc` with
no backup, never consults `$ZDOTDIR`, and appends an unconditional `compinit`. Emit the script
instead and let the user or packager place it:

    _CLI_COMPLETE=source_zsh cli > "${ZDOTDIR:-$HOME}/completions/_cli"

Note `source_zsh`, not `zsh_source` — typer inverts Click 8's order for backwards compatibility.
"""

import sys

import typer

from claude.currency import currency
from claude.geo import geo
from claude.typer_entrypoint import run_app

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.command("geo")(geo)
app.command("currency")(currency)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    return run_app(app, argv, prog_name="cli")


if __name__ == "__main__":
    sys.exit(main())
