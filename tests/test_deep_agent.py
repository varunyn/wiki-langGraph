"""Smoke tests for Deep Agents factory (skills + filesystem backend)."""

from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.deep_agent import (
    bundled_skills_dir,
    create_wiki_deep_agent,
    wiki_filesystem_backend,
)


def test_bundled_skills_contains_skill_md() -> None:
    """Packaged Agent Skills layout should include obsidian-markdown/SKILL.md."""
    skill = bundled_skills_dir() / "obsidian-markdown" / "SKILL.md"
    assert skill.is_file()
    assert "name: obsidian-markdown" in skill.read_text(encoding="utf-8")


def test_wiki_filesystem_backend_uses_composite_without_project_skills(
    tmp_path: Path,
) -> None:
    """Empty project should route /skills/ to bundled package skills."""
    cfg = Settings(project_root=tmp_path)
    backend = wiki_filesystem_backend(cfg)
    assert type(backend).__name__ == "CompositeBackend"


def test_wiki_filesystem_backend_plain_when_project_has_skill(tmp_path: Path) -> None:
    """Project with skills/obsidian-markdown/SKILL.md should use a single FS backend."""
    skill = tmp_path / "skills" / "obsidian-markdown" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: t\n---\n\n# X\n", encoding="utf-8")
    cfg = Settings(project_root=tmp_path)
    backend = wiki_filesystem_backend(cfg)
    assert type(backend).__name__ == "FilesystemBackend"


def test_create_wiki_deep_agent_returns_compiled_graph(tmp_path: Path) -> None:
    """Deep agent should build without invoking the network."""
    cfg = Settings(
        project_root=tmp_path,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="llama3.2",
    )
    agent = create_wiki_deep_agent(settings=cfg)
    assert hasattr(agent, "invoke")
