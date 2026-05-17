import logging
import os
import sys

_FORMATTER = logging.Formatter("%(levelname)-8s %(name)s: %(message)s")


def get_logger(name: str) -> logging.Logger:
    """Return a stderr logger for the given name.

    Level is controlled by the LOG_LEVEL environment variable (default INFO).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_FORMATTER)
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    return logger
