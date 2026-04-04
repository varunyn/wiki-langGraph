"""Tests for Obsidian markdown skill loading for LLM prompts."""

from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.obsidian_prompt import (
    load_obsidian_markdown_skill_text,
    wiki_llm_system_instructions,
)


def test_load_bundled_skill_contains_frontmatter_and_ofm() -> None:
    """Bundled skill text should describe YAML frontmatter and Obsidian extensions."""
    text = load_obsidian_markdown_skill_text(settings=Settings())
    assert "Properties (Frontmatter)" in text
    assert "[[Note Name]]" in text
    assert "---" in text


def test_load_raw_includes_skill_frontmatter(tmp_path: Path) -> None:
    """With raw=True, YAML frontmatter from SKILL.md should be preserved."""
    skill = tmp_path / "skills" / "obsidian-markdown" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: test-skill\n---\n\n# Body\n", encoding="utf-8")
    raw = load_obsidian_markdown_skill_text(
        settings=Settings(project_root=tmp_path),
        raw=True,
    )
    assert raw.startswith("---")
    assert "name: test-skill" in raw


def test_load_custom_skill_path(tmp_path: Path) -> None:
    """Configured path should be used instead of the bundled file."""
    custom = tmp_path / "custom.md"
    custom.write_text("# Custom skill\n", encoding="utf-8")
    text = load_obsidian_markdown_skill_text(
        settings=Settings(obsidian_markdown_skill_path=custom),
    )
    assert text.strip() == "# Custom skill"


def test_wiki_llm_system_instructions_appends_task() -> None:
    """Optional task hint should appear after the skill body."""
    out = wiki_llm_system_instructions(
        task_hint="Summarize the raw files into Index.md.",
        settings=Settings(obsidian_markdown_skill_path=None),
    )
    assert "Properties (Frontmatter)" in out
    assert "Summarize the raw files" in out
