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


def test_llm_compile_review_default_off() -> None:
    """Review mode is opt-in for backward compatibility."""
    assert Settings().llm_compile_review == "off"


def test_llm_compile_review_accepts_supported_modes() -> None:
    """Review mode accepts off/risky/all and normalizes case."""
    assert Settings(llm_compile_review="RISKY").llm_compile_review == "risky"
    assert Settings(llm_compile_review="all").llm_compile_review == "all"


def test_llm_compile_review_invalid_falls_back_to_off() -> None:
    """Unexpected review mode values fall back to current behavior."""
    assert Settings(llm_compile_review="maybe").llm_compile_review == "off"


def test_output_profile_default_and_supported_modes() -> None:
    """Output profile defaults to OKF and normalizes supported modes."""
    assert Settings().output_profile == "okf"
    assert Settings(output_profile="OKF").output_profile == "okf"
    assert Settings(output_profile="obsidian").output_profile == "obsidian"


def test_output_profile_invalid_falls_back_to_okf() -> None:
    """Unexpected profile values preserve canonical OKF behavior."""
    assert Settings(output_profile="unknown").output_profile == "okf"
    assert Settings(output_profile="hybrid").output_profile == "okf"
