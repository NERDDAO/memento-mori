"""Tests for the logging module."""

import logging
from memento.log import get_logger


def test_get_logger_returns_logger():
    logger = get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_get_logger_has_handler():
    logger = get_logger("test.handler")
    assert len(logger.handlers) >= 1


def test_get_logger_default_level():
    logger = get_logger("test.level")
    assert logger.level == logging.INFO


def test_get_logger_same_instance():
    logger1 = get_logger("test.same")
    logger2 = get_logger("test.same")
    assert logger1 is logger2
