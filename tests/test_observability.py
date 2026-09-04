"""Tests for optional Langfuse client configuration."""

import os
from unittest.mock import patch

from wiki_langgraph.observability import _langfuse_client


def test_langfuse_client_sets_service_name_before_initialization(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class FakeLangfuse:
        def __init__(self, **kwargs: object) -> None:
            captured["service_name"] = os.environ.get("OTEL_SERVICE_NAME")
            captured["kwargs"] = kwargs

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    _langfuse_client.cache_clear()
    with patch("langfuse.Langfuse", FakeLangfuse):
        _langfuse_client("public", "secret", "http://localhost", "test", "release", "wiki-test")

    assert captured["service_name"] == "wiki-test"
    _langfuse_client.cache_clear()
