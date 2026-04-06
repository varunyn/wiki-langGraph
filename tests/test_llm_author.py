from types import SimpleNamespace
from unittest.mock import patch

from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.llm_author import _inject_provenance_frontmatter
from wiki_langgraph.llm_author import author_raw_to_wiki_markdown
from wiki_langgraph.obsidian_prompt import wiki_llm_system_instructions


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


def test_system_instructions_require_wikilinks_for_known_vault_notes(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path)
    prompt = wiki_llm_system_instructions(
        task_hint="Compile a source document into a note.",
        settings=settings,
    )

    assert "use an actual `[[wikilink]]` instead of plain text" in prompt
    assert "Do not leave navigable note references as plain prose" in prompt


def test_author_prompt_includes_known_vault_titles(tmp_path: Path) -> None:
    captured_messages: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, messages: list[object]) -> SimpleNamespace:
            captured_messages.extend(messages)
            return SimpleNamespace(content="# Title\n\nBody")

    settings = Settings(
        project_root=tmp_path,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
    )

    with patch("wiki_langgraph.llm_author.ChatOpenAI", FakeChatOpenAI):
        author_raw_to_wiki_markdown(
            "raw body",
            "notes/source.md",
            settings=settings,
            known_note_titles=["AI Agent Prompt Design", "Knowledge Base Indexing for Agents"],
        )

    assert len(captured_messages) == 2
    human = captured_messages[1]
    content = human.content if hasattr(human, "content") else ""
    assert "KNOWN_VAULT_NOTES" in content
    assert "AI Agent Prompt Design" in content
    assert "Knowledge Base Indexing for Agents" in content


def test_author_prompt_includes_quality_and_selective_linking_rules(tmp_path: Path) -> None:
    captured_messages: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, messages: list[object]) -> SimpleNamespace:
            captured_messages.extend(messages)
            return SimpleNamespace(content="# Title\n\nBody")

    settings = Settings(
        project_root=tmp_path,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="test-model",
    )

    with patch("wiki_langgraph.llm_author.ChatOpenAI", FakeChatOpenAI):
        author_raw_to_wiki_markdown("raw body", "notes/source.md", settings=settings)

    system = captured_messages[0]
    content = system.content if hasattr(system, "content") else ""
    assert "Produce a clean, readable note for both humans and future AI retrieval." in content
    assert "Prefer concise, information-dense writing over filler" in content
    assert "Link selectively: prefer a small number of high-value wikilinks" in content
    assert "Do not create wikilinks for incidental mentions" in content
