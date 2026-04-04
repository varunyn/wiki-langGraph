"""Tests for optional file logging."""

import logging
from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.logging_config import configure_logging, parse_log_level


def test_parse_log_level() -> None:
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO
    assert parse_log_level("bogus") == logging.INFO


def test_configure_logging_writes(tmp_path: Path) -> None:
    """Configured file path should receive log records."""
    log_path = tmp_path / "out.log"
    cfg = Settings(log_file=log_path, log_level="INFO")
    configure_logging(cfg)
    logging.getLogger("wiki_langgraph.cli").info("hello from test")
    text = log_path.read_text(encoding="utf-8")
    assert "hello from test" in text
    assert "INFO" in text


def test_configure_skips_without_log_file() -> None:
    """No log_file should not attach handlers."""
    pkg = logging.getLogger("wiki_langgraph")
    pkg.handlers.clear()
    configure_logging(Settings(log_file=None))
    assert len(pkg.handlers) == 0
