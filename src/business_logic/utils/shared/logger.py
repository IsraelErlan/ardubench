import logging
import os
import sys

_FORMATTER = logging.Formatter('%(levelname)-8s %(name)s: %(message)s')
_LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()


def get_logger(name: str) -> logging.Logger:
    """Return a stderr logger for the given name.

    Level is controlled by the LOG_LEVEL environment variable (default INFO).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_FORMATTER)
        logger.addHandler(handler)
    logger.setLevel(_LOG_LEVEL)
    return logger
