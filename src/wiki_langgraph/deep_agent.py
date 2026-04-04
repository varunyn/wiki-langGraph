"""LangChain Deep Agents integration with Agent Skills (progressive disclosure).

See https://docs.langchain.com/oss/python/deepagents/skills and
https://agentskills.io/specification
"""

from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from wiki_langgraph.config import Settings, load_settings


def bundled_skills_dir() -> Path:
    """Directory containing packaged ``obsidian-markdown/SKILL.md`` (Agent Skills layout)."""
    return Path(__file__).resolve().parent / "skills"


def wiki_filesystem_backend(settings: Settings) -> CompositeBackend | FilesystemBackend:
    """Backend for the wiki: project files as default, bundled skills when project has none.

    If ``<project_root>/skills/obsidian-markdown/SKILL.md`` exists, the whole
    project tree is exposed (including that skill). Otherwise ``/skills/`` is
    routed to the bundled package skills so Deep Agents still discover skills
    after ``pip install`` without copying files.
    """
    root = settings.project_root.resolve()
    project_skill = root / "skills" / "obsidian-markdown" / "SKILL.md"
    if project_skill.is_file():
        return FilesystemBackend(root_dir=str(root), virtual_mode=True)
    return CompositeBackend(
        default=FilesystemBackend(root_dir=str(root), virtual_mode=True),
        routes={"/skills/": FilesystemBackend(root_dir=str(bundled_skills_dir()), virtual_mode=True)},
    )


def chat_model_from_settings(settings: Settings) -> ChatOpenAI:
    """Build a :class:`~langchain_openai.ChatOpenAI` from wiki settings (Ollama, OpenAI, etc.)."""
    kwargs: dict[str, str | float] = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key,
        "request_timeout": settings.llm_request_timeout_sec,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base
    return ChatOpenAI(**kwargs)


def create_wiki_deep_agent(
    settings: Settings | None = None,
    *,
    model: BaseChatModel | str | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Create a Deep Agent with ``/skills/`` wired to Obsidian OFM (progressive disclosure).

    The agent loads skill metadata from ``SKILL.md`` frontmatter and reads full
    instructions on demand, matching the Deep Agents skills pattern.

    Args:
        settings: Wiki paths and LLM endpoints; defaults from env / ``.env``.
        model: Chat model or ``provider:model`` string. Defaults to
            :func:`chat_model_from_settings`.
        system_prompt: Extra instructions prepended to the base deep-agent prompt.

    Returns:
        A compiled LangGraph agent ready to ``invoke`` / ``astream``.
    """
    cfg = settings or load_settings()
    backend = wiki_filesystem_backend(cfg)
    resolved_model = model if model is not None else chat_model_from_settings(cfg)
    return create_deep_agent(
        model=resolved_model,
        backend=backend,
        skills=["/skills/"],
        system_prompt=system_prompt,
    )
