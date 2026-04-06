from types import SimpleNamespace
from unittest.mock import patch

from wiki_langgraph.config import Settings
from wiki_langgraph.llm_author import _inject_provenance_frontmatter
from wiki_langgraph.llm_author import author_raw_to_wiki_markdown


def test_provenance_prepended_when_no_frontmatter() -> None:
    """compiled_from is added as a new frontmatter block when none exists."""
    out = _inject_provenance_frontmatter("# Note\n\nBody.\n", "raw/note.md")
    assert "compiled_from: raw/note.md" in out
    assert out.startswith("---\n")
    assert "# Note" in out


def test_provenance_merged_into_existing_frontmatter() -> None:
    """compiled_from is inserted inside an existing frontmatter block."""
    md = "---\ntitle: My Note\ntags: [a]\n---\n\n# My Note\n"
    out = _inject_provenance_frontmatter(md, "raw/my-note.md")
    assert out.count("---") >= 2
    assert "compiled_from: raw/my-note.md" in out
    assert "title: My Note" in out
    assert "# My Note" in out


def test_provenance_updates_existing_compiled_from() -> None:
    """If compiled_from already exists in frontmatter it is updated, not duplicated."""
    md = "---\ntitle: T\ncompiled_from: raw/old.md\n---\n\nBody.\n"
    out = _inject_provenance_frontmatter(md, "raw/new.md")
    assert out.count("compiled_from:") == 1
    assert "raw/new.md" in out
    assert "raw/old.md" not in out


def test_provenance_body_preserved() -> None:
    """Document body is intact after frontmatter injection."""
    body = "# Hello\n\nSome [[link]] text.\n"
    out = _inject_provenance_frontmatter(body, "notes/hello.md")
    assert "Some [[link]] text." in out


def test_author_raw_to_wiki_markdown_passes_expected_chatopenai_kwargs() -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(content="# Title\n\nBody")

    settings = Settings(
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
        openai_api_key="test-key",
        llm_request_timeout_sec=123.0,
    )

    with patch("wiki_langgraph.llm_author.ChatOpenAI", FakeChatOpenAI):
        out = author_raw_to_wiki_markdown("raw body", "notes/source.md", settings=settings)

    assert captured == {
        "model": "test-model",
        "api_key": "test-key",
        "temperature": 0.3,
        "request_timeout": 123.0,
        "base_url": "http://127.0.0.1:11434/v1",
    }
    assert "compiled_from: notes/source.md" in out


def test_author_raw_to_wiki_markdown_falls_back_to_raw_text_on_llm_error() -> None:
    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _messages: list[object]) -> SimpleNamespace:
            raise RuntimeError("boom")

    settings = Settings(
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
    )

    with patch("wiki_langgraph.llm_author.ChatOpenAI", FakeChatOpenAI):
        out = author_raw_to_wiki_markdown("raw body", "notes/source.md", settings=settings)

    assert out == "raw body"
