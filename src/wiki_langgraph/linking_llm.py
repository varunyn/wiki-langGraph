"""Semantic related-note suggestions via OpenAI-compatible local LLM (e.g. Ollama)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypedDict

from wiki_langgraph.config import Settings
from wiki_langgraph.linking import wikilink_display_name

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 14_000
MAX_CATALOG_NOTES = 400


class SemanticRelatedOutput(TypedDict):
    related: list[str]


ChatOpenAIFactory = Callable[..., object]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n…(truncated)…\n"


def _match_catalog_entry(suggestion: str, catalog: list[str]) -> str | None:
    """Map a model string to a vault relpath from the catalog."""
    s = suggestion.strip().strip('"').strip("'")
    if not s:
        return None
    s_norm = s.replace("\\", "/")
    for rel in catalog:
        if rel == s_norm:
            return rel
        if wikilink_display_name(rel) == s_norm:
            return rel
        if rel.lower().endswith(s_norm.lower() + ".md"):
            return rel
        if s_norm.lower().endswith(".md") and rel.lower() == s_norm.lower():
            return rel
    return None


def suggest_semantic_related(
    settings: Settings,
    current_relpath: str,
    body: str,
    other_relpaths: list[str],
) -> list[str]:
    """Ask the local/chat model which other notes relate to this note's content.

    Returns a list of catalog ``relpaths`` (never includes ``current_relpath``).
    On failure or empty response, returns ``[]``.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    catalog = [p for p in sorted(other_relpaths) if p != current_relpath]
    if not catalog:
        return []

    catalog_lines = "\n".join(f"- {wikilink_display_name(p)}" for p in catalog[:MAX_CATALOG_NOTES])
    body_t = _truncate(body, MAX_BODY_CHARS)

    system = (
        "You connect notes in an Obsidian vault. Given one note's path and body, "
        "pick other notes from the CATALOG that are substantively related (themes, references, "
        "same project, etc.). Use ONLY catalog entries. Return `related` using paths exactly as in the catalog lines "
        "(path without .md, matching the vault-relative form). "
        "Prefer 0–8 links; use [] if nothing fits."
    )
    human = (
        f"CURRENT_NOTE_PATH: {wikilink_display_name(current_relpath)}\n\n"
        f"CATALOG (pick only from these):\n{catalog_lines}\n\n"
        f"NOTE_BODY:\n{body_t}"
    )

    try:
        llm_factory: ChatOpenAIFactory = ChatOpenAI
        llm_kwargs = {
            "model": settings.llm_model,
            "api_key": settings.openai_api_key,
            "temperature": 0.2,
            "request_timeout": settings.llm_request_timeout_sec,
        }
        if settings.openai_api_base:
            llm_kwargs["base_url"] = settings.openai_api_base
        llm = llm_factory(**llm_kwargs)
        structured_llm = llm.with_structured_output(SemanticRelatedOutput)
        data = structured_llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        if not isinstance(data, dict):
            return []
        raw_list = data.get("related")
        if not isinstance(raw_list, list):
            return []
        out: list[str] = []
        for item in raw_list:
            if not isinstance(item, str):
                continue
            matched = _match_catalog_entry(item, catalog)
            if matched and matched not in out:
                out.append(matched)
        logger.debug(
            "semantic_links ok path=%s edges=%s",
            current_relpath,
            len(out),
        )
        return out
    except Exception as exc:
        logger.warning("Semantic link suggestion failed for %s: %s", current_relpath, exc)
        return []
