"""Load Obsidian Flavored Markdown instructions for LLM system prompts."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from wiki_langgraph.config import Settings, load_settings


def _strip_yaml_frontmatter(markdown: str) -> str:
    """Remove a leading YAML block (``---`` ... ``---``) when present."""
    lines = markdown.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return markdown
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return markdown


def resolve_obsidian_markdown_skill_path(settings: Settings) -> Path:
    """Return the path to the Obsidian skill file (``SKILL.md`` or custom override)."""
    if settings.obsidian_markdown_skill_path is not None:
        return settings.obsidian_markdown_skill_path
    project = settings.project_root / "skills" / "obsidian-markdown" / "SKILL.md"
    if project.is_file():
        return project
    return Path(__file__).resolve().parent / "skills" / "obsidian-markdown" / "SKILL.md"


def load_obsidian_markdown_skill_text(settings: Settings | None = None, *, raw: bool = False) -> str:
    """Load Obsidian markdown skill text for use as LLM system context.

    Resolves :func:`resolve_obsidian_markdown_skill_path`, then reads the file.
    When ``raw`` is False (default), strips YAML frontmatter so plain chat APIs
    receive only instruction body (Deep Agents still use ``SKILL.md`` on disk).

    Uses :attr:`Settings.obsidian_markdown_skill_path` when set; otherwise
    ``<project>/skills/obsidian-markdown/SKILL.md`` if present, else the bundled
    package copy (Agent Skills layout per deepagents).
    """
    cfg = settings or load_settings()
    path = resolve_obsidian_markdown_skill_path(cfg)

    if cfg.obsidian_markdown_skill_path is not None:
        if not path.is_file():
            msg = f"Obsidian markdown skill file not found: {path}"
            raise FileNotFoundError(msg)
        text = path.read_text(encoding="utf-8")
        return text if raw else _strip_yaml_frontmatter(text)

    if path.is_file():
        text = path.read_text(encoding="utf-8")
        return text if raw else _strip_yaml_frontmatter(text)

    try:
        text = (
            resources.files("wiki_langgraph")
            .joinpath("skills/obsidian-markdown/SKILL.md")
            .read_text(encoding="utf-8")
        )
    except OSError as exc:
        msg = f"Obsidian markdown skill file not found: {path}"
        raise FileNotFoundError(msg) from exc
    return text if raw else _strip_yaml_frontmatter(text)


def wiki_llm_system_instructions(
    *,
    task_hint: str = "",
    settings: Settings | None = None,
) -> str:
    """Build system instructions for wiki compilation: OFM skill body plus optional task text.

    Use as the system message when calling an OpenAI-compatible chat API to
    generate vault markdown so output follows Obsidian frontmatter and OFM.
    """
    skill = load_obsidian_markdown_skill_text(settings=settings)
    hint = task_hint.strip()
    if not hint:
        return skill
    return f"{skill}\n\n---\n\n## Task\n\n{hint}\n"
