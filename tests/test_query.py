"""Tests for query and save-as-note workflow."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.query import answer_query
from wiki_langgraph.query import research_query
from wiki_langgraph.query import save_query_answer
from wiki_langgraph.query import save_research_brief
from wiki_langgraph.query import search_wiki_context


def _settings(tmp_path: Path) -> Settings:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    return Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
        openai_api_key="test-key",
    )


def test_search_wiki_context_ranks_relevant_notes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.wiki_dir() / "RAG Failure Analysis Playbook.md").write_text(
        "# RAG Failure Analysis Playbook\n\nRetrieval ranking and chunking failures.",
        encoding="utf-8",
    )
    (settings.wiki_dir() / "Weekly Grocery List.md").write_text(
        "# Weekly Grocery List\n\nRice and lentils.",
        encoding="utf-8",
    )

    results = search_wiki_context("How do I debug retrieval ranking failures?", settings=settings)

    assert [result.relpath for result in results] == ["RAG Failure Analysis Playbook.md"]
    assert "Retrieval ranking" in results[0].excerpt


def test_answer_query_calls_chat_model_with_context(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.wiki_dir() / "RAG Failure Analysis Playbook.md").write_text(
        "# RAG Failure Analysis Playbook\n\nUse retrieved evidence to classify failures.",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def invoke(self, messages: list[object]) -> SimpleNamespace:
            captured["messages"] = messages
            return SimpleNamespace(text="Use [[RAG Failure Analysis Playbook]] and inspect retrieval.")

    with patch("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI):
        result = answer_query("How should I debug RAG?", settings=settings)

    assert "Use [[RAG Failure Analysis Playbook]]" in result.answer
    assert result.sources[0].relpath == "RAG Failure Analysis Playbook.md"
    assert captured["kwargs"] == {
        "model": "test-model",
        "api_key": "test-key",
        "temperature": 0.2,
        "request_timeout": 300.0,
        "base_url": "http://127.0.0.1:11434/v1",
    }
    human = captured["messages"][1]
    assert "RAG Failure Analysis Playbook.md" in human.content


def test_answer_query_records_retrieval_observation(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    settings = _settings(tmp_path)
    (settings.wiki_dir() / "Retrieval.md").write_text(
        "# Retrieval\n\nBounded lexical retrieval.",
        encoding="utf-8",
    )
    observations: list[dict[str, object]] = []

    class FakeSpan:
        def __init__(self, record: dict[str, object]) -> None:
            self.record = record

        def update(self, **kwargs: object) -> None:
            self.record.update(kwargs)

    @contextmanager
    def fake_trace_operation(_settings: Settings, **kwargs: object):  # noqa: ANN202
        record = dict(kwargs)
        observations.append(record)
        yield FakeSpan(record)

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(text="Use [[Retrieval]].")

    monkeypatch.setattr("wiki_langgraph.query.trace_operation", fake_trace_operation)
    monkeypatch.setattr("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI)

    answer_query("How is retrieval bounded?", settings=settings, top_k=2)

    assert observations[0]["name"] == "wiki.query"
    assert observations[0]["root"] is True
    assert observations[1]["name"] == "wiki.retrieve"
    assert observations[1]["observation_type"] == "retriever"
    assert observations[1]["output"] == {"sources": ["Retrieval.md"]}


def test_save_query_answer_writes_to_queries_folder(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = answer_query.__annotations__  # keep import used by static checkers
    del result
    saved = save_query_answer(
        question="How should I debug RAG failures?",
        answer="Use [[RAG Failure Analysis Playbook]].",
        source_relpaths=["RAG Failure Analysis Playbook.md", "Agent Evaluation and Feedback Loops.md"],
        settings=settings,
    )

    assert saved.as_posix().endswith("Queries/How should I debug RAG failures.md")
    text = saved.read_text(encoding="utf-8")
    assert "source_question: How should I debug RAG failures?" in text
    assert "# How should I debug RAG failures?" in text
    assert "Use [[RAG Failure Analysis Playbook]]." in text
    assert "- [[RAG Failure Analysis Playbook]]" in text
    assert "- [[Agent Evaluation and Feedback Loops]]" in text


def test_research_query_requests_structured_brief(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.wiki_dir() / "RAG Failure Analysis Playbook.md").write_text(
        "# RAG Failure Analysis Playbook\n\nRetrieval ranking failures.",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, messages: list[object]) -> SimpleNamespace:
            captured["messages"] = messages
            return SimpleNamespace(
                text=(
                    "# Research Brief\n\n"
                    "## Summary\n\nUse [[RAG Failure Analysis Playbook]].\n\n"
                    "## Key Findings\n\n- Inspect retrieval.\n"
                )
            )

    with patch("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI):
        result = research_query("Compare RAG failures and evaluation loops", settings=settings)

    assert result.answer.startswith("# Research Brief")
    assert result.sources[0].relpath == "RAG Failure Analysis Playbook.md"
    human = captured["messages"][1]
    system = captured["messages"][0]
    assert "Research Brief" in human.content
    assert "Open Questions" in human.content
    assert "approval boundaries" in system.content
    assert "before setting thresholds" in system.content
    assert "Every Key Findings bullet" in system.content


def test_save_research_brief_writes_to_research_folder(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    saved = save_research_brief(
        question="Compare RAG failures and evaluation loops",
        brief="# Research Brief\n\n## Summary\n\nUse [[RAG Failure Analysis Playbook]].",
        source_relpaths=["RAG Failure Analysis Playbook.md"],
        settings=settings,
    )

    assert saved.as_posix().endswith("Research/Compare RAG failures and evaluation loops.md")
    text = saved.read_text(encoding="utf-8")
    assert "tags:\n  - research\n  - ai" in text
    assert "source_question: Compare RAG failures and evaluation loops" in text
    assert "# Research Brief" in text
    assert "- [[RAG Failure Analysis Playbook]]" in text
