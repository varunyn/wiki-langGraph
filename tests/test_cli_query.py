"""CLI tests for query command."""

from pathlib import Path
from types import SimpleNamespace

from wiki_langgraph.cli import main


def _query_env(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (wiki / "RAG Failure Analysis Playbook.md").write_text(
        "# RAG Failure Analysis Playbook\n\nRetrieval ranking failures.",
        encoding="utf-8",
    )
    monkeypatch.setenv("WIKI_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("WIKI_DATA_RAW_DIR", str(raw))
    monkeypatch.setenv("WIKI_DATA_WIKI_DIR", str(wiki))
    monkeypatch.setenv("WIKI_OPENAI_API_BASE", "http://127.0.0.1:11434/v1")


def test_query_cli_prints_answer(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    _query_env(monkeypatch, tmp_path)

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(text="Inspect retrieval ranking.")

    monkeypatch.setattr("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI)

    assert main(["query", "How do I debug RAG?"]) == 0

    out = capsys.readouterr().out
    assert "Inspect retrieval ranking." in out
    assert "Sources:" in out
    assert "RAG Failure Analysis Playbook.md" in out


def test_query_cli_save_writes_raw_query_note(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    _query_env(monkeypatch, tmp_path)

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(text="Use [[RAG Failure Analysis Playbook]].")

    monkeypatch.setattr("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI)

    assert main(["query", "How do I debug RAG?", "--save"]) == 0

    saved = tmp_path / "raw" / "Queries" / "How do I debug RAG.md"
    assert saved.is_file()
    assert "Use [[RAG Failure Analysis Playbook]]." in saved.read_text(encoding="utf-8")
    assert f"saved: {saved}" in capsys.readouterr().out


def test_research_cli_save_writes_raw_research_note(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    _query_env(monkeypatch, tmp_path)

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(text="# Research Brief\n\n## Summary\n\nUse [[RAG Failure Analysis Playbook]].")

    monkeypatch.setattr("wiki_langgraph.query.ChatOpenAI", FakeChatOpenAI)

    assert main(["research", "Compare RAG failures and eval loops", "--save"]) == 0

    saved = tmp_path / "raw" / "Research" / "Compare RAG failures and eval loops.md"
    assert saved.is_file()
    assert "# Research Brief" in saved.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "Research Brief" in out
    assert f"saved: {saved}" in out
