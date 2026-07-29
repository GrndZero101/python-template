"""Report the current user and hostname.

Exit codes: 0 on success, 1 if the identity cannot be determined, 2 on usage error.
"""

import argparse
import dataclasses
import getpass
import json
import logging
import socket
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who this process is running as, and where."""

    user: str
    host: str


def current_identity(
    get_user: Callable[[], str] = getpass.getuser,
    get_host: Callable[[], str] = socket.gethostname,
) -> Identity:
    """Return the current user and hostname.

    Both lookups are injected so tests can pin them without touching the
    environment, and so either can be substituted from a breakpoint.
    """
    return Identity(user=get_user(), host=get_host())


def format_identity(identity: Identity, *, as_json: bool = False) -> str:
    """Render `identity` for stdout, as JSON or as `user@host`."""
    if as_json:
        return json.dumps(dataclasses.asdict(identity))
    return f"{identity.user}@{identity.host}"


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="whoami",
        description="Print the current user and hostname.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON object instead of user@host",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log details to stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        identity = current_identity()
    except OSError:
        logger.exception("could not determine the current user or hostname")
        return 1

    logger.debug("resolved user=%s host=%s", identity.user, identity.host)
    sys.stdout.write(f"{format_identity(identity, as_json=args.json)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
