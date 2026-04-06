from unittest.mock import patch

from wiki_langgraph.config import Settings
from wiki_langgraph.linking_llm import SemanticRelatedOutput
from wiki_langgraph.linking_llm import suggest_semantic_related


def test_suggest_semantic_related_passes_expected_chatopenai_kwargs() -> None:
    captured: dict[str, object] = {}
    schema_holder: dict[str, type[SemanticRelatedOutput]] = {}

    class FakeStructuredChatOpenAI:
        def invoke(self, _messages: list[object]) -> dict[str, object]:
            return {"related": ["topic-b"]}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def with_structured_output(
            self, schema: type[SemanticRelatedOutput], **kwargs: object
        ) -> FakeStructuredChatOpenAI:
            schema_holder["schema"] = schema
            assert kwargs == {}
            return FakeStructuredChatOpenAI()

    settings = Settings(
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
        openai_api_key="test-key",
        llm_request_timeout_sec=45.0,
    )

    with patch("langchain_openai.ChatOpenAI", FakeChatOpenAI):
        out = suggest_semantic_related(
            settings,
            "topic-a.md",
            "body",
            ["topic-a.md", "topic-b.md"],
        )

    assert captured == {
        "model": "test-model",
        "api_key": "test-key",
        "temperature": 0.2,
        "request_timeout": 45.0,
        "base_url": "http://127.0.0.1:11434/v1",
    }
    assert schema_holder["schema"] is SemanticRelatedOutput
    assert out == ["topic-b.md"]


def test_suggest_semantic_related_returns_empty_on_llm_error() -> None:
    class FakeStructuredChatOpenAI:
        def invoke(self, _messages: list[object]) -> dict[str, object]:
            raise RuntimeError("boom")

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def with_structured_output(self, _schema: object, **_kwargs: object) -> FakeStructuredChatOpenAI:
            return FakeStructuredChatOpenAI()

    settings = Settings(
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
    )

    with patch("langchain_openai.ChatOpenAI", FakeChatOpenAI):
        out = suggest_semantic_related(
            settings,
            "topic-a.md",
            "body",
            ["topic-a.md", "topic-b.md"],
        )

    assert out == []
