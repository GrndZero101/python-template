"""Route stdlib `logging` (used by httpx and other dependencies) into loguru.

Vendored boilerplate, not an example of house style: the frame-walking loop is
the standard `InterceptHandler` recipe from loguru's own documentation.
"""

import logging
import sys
from typing import override

from loguru import logger

DEFAULT_FORMAT = "<level>{level: <8}</level> {name}: <level>{message}</level>"


class InterceptHandler(logging.Handler):
    """Forward stdlib logging records to loguru."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        """Re-emit `record` through loguru, preserving level and call site."""
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(*, verbose: bool = False) -> None:
    """Configure loguru as the single sink for this process, on stderr.

    Also installs the `InterceptHandler` so dependencies still using stdlib
    `logging` (httpx, etc.) are not silently dropped.
    """
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "WARNING", format=DEFAULT_FORMAT)
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


if __name__ == "__main__":
    configure_logging(verbose=True)
