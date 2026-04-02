"""Structured logging for the memento engine."""

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with a consistent format.

    Log level is controlled by the LOG_LEVEL env var (default: INFO).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    return logger
