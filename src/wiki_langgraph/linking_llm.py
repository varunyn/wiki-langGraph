"""Semantic related-note suggestions via OpenAI-compatible local LLM (e.g. Ollama)."""

from __future__ import annotations

import json
import logging
import re
from wiki_langgraph.config import Settings
from wiki_langgraph.linking import wikilink_display_name

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 14_000
MAX_CATALOG_NOTES = 400


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n…(truncated)…\n"


def _parse_json_object(raw: str) -> dict[str, object]:
    """Extract JSON object from model output (handles optional markdown fences)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


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
        "same project, etc.). Use ONLY catalog entries. Respond with JSON only: "
        '{"related": ["path/or/Note", ...]} using paths exactly as in the catalog lines '
        "(path without .md, matching the vault-relative form). "
        "Prefer 0–8 links; use [] if nothing fits. No prose outside JSON."
    )
    human = (
        f"CURRENT_NOTE_PATH: {wikilink_display_name(current_relpath)}\n\n"
        f"CATALOG (pick only from these):\n{catalog_lines}\n\n"
        f"NOTE_BODY:\n{body_t}"
    )

    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key,
        "temperature": 0.2,
        "request_timeout": settings.llm_request_timeout_sec,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base

    try:
        llm = ChatOpenAI(**kwargs)
        msg = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        data = _parse_json_object(raw)
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
