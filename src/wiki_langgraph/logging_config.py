"""Optional file logging for the ``wiki_langgraph`` package (CLI and graph nodes)."""

from __future__ import annotations

import logging
from pathlib import Path

from wiki_langgraph.config import Settings

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_log_level(name: str) -> int:
    """Map ``DEBUG`` / ``INFO`` / ``WARNING`` / ``ERROR`` to logging levels."""
    level = getattr(logging, name.upper(), None)
    if isinstance(level, int):
        return level
    return logging.INFO


def configure_logging(settings: Settings) -> None:
    """Attach a file handler to the ``wiki_langgraph`` logger when ``log_file`` is set.

    Safe to call once per process (replaces prior handlers on that logger). Child
    loggers such as ``wiki_langgraph.nodes`` propagate here.
    """
    if settings.log_file is None:
        return

    path = Path(settings.log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    level = parse_log_level(settings.log_level)

    pkg = logging.getLogger("wiki_langgraph")
    pkg.handlers.clear()
    pkg.setLevel(level)
    pkg.propagate = False

    handler = logging.FileHandler(path, encoding="utf-8", mode="a")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    pkg.addHandler(handler)
