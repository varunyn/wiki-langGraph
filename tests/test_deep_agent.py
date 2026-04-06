"""Smoke tests for Deep Agents factory (skills + filesystem backend)."""

from pathlib import Path
from unittest.mock import patch

from wiki_langgraph.config import Settings
from wiki_langgraph.deep_agent import (
    bundled_skills_dir,
    chat_model_from_settings,
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


def test_chat_model_from_settings_passes_expected_chatopenai_kwargs(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    cfg = Settings(
        project_root=tmp_path,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="llama3.2",
        openai_api_key="test-key",
        llm_request_timeout_sec=99.0,
    )

    with patch("wiki_langgraph.deep_agent.ChatOpenAI", FakeChatOpenAI):
        chat_model_from_settings(cfg)

    assert captured == {
        "model": "llama3.2",
        "api_key": "test-key",
        "request_timeout": 99.0,
        "base_url": "http://127.0.0.1:11434/v1",
    }


def test_create_wiki_deep_agent_passes_expected_factory_kwargs(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    cfg = Settings(
        project_root=tmp_path,
        openai_api_base="http://127.0.0.1:11434/v1",
        llm_model="llama3.2",
    )

    with patch("wiki_langgraph.deep_agent.create_deep_agent", fake_create_deep_agent):
        agent = create_wiki_deep_agent(settings=cfg, system_prompt="extra")

    assert agent is not None
    assert captured["skills"] == ["/skills/"]
    assert captured["system_prompt"] == "extra"
    assert type(captured["backend"]).__name__ == "CompositeBackend"
    assert type(captured["model"]).__name__ == "ChatOpenAI"
