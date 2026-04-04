"""Settings validation for LLM compile."""

import pytest

from wiki_langgraph.config import Settings


def test_llm_compile_requires_openai_base() -> None:
    """Enabling llm_compile without an API base raises a clear error."""
    with pytest.raises(ValueError, match="WIKI_OPENAI_API_BASE"):
        Settings(llm_compile=True, openai_api_base=None)


def test_llm_compile_ok_with_base() -> None:
    """llm_compile is valid when a base URL is set."""
    s = Settings(llm_compile=True, openai_api_base="http://127.0.0.1:8080/v1")
    assert s.llm_compile is True


def test_llm_request_timeout_default() -> None:
    """Field default is documented; ``.env`` may override at runtime."""
    assert Settings.model_fields["llm_request_timeout_sec"].default == 300.0


def test_llm_compile_max_workers_default() -> None:
    """Field default is sequential authoring (local inference is usually single-stream)."""
    assert Settings.model_fields["llm_compile_max_workers"].default == 1
