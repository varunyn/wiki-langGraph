"""LLM-assisted authoring: turn raw markdown into Obsidian-style wiki pages."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from wiki_langgraph.config import Settings
from wiki_langgraph.obsidian_prompt import wiki_llm_system_instructions

logger = logging.getLogger(__name__)

MAX_SOURCE_CHARS = 48_000
MAX_EXISTING_CHARS = 16_000


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 30] + "\n\n…(source truncated for context window)…\n"


def _inject_provenance_frontmatter(markdown: str, source_rel: str) -> str:
    """Ensure ``compiled_from: <source_rel>`` appears in YAML frontmatter.

    If the markdown already has a frontmatter block, the key is inserted (or updated)
    inside it.  Otherwise a minimal frontmatter block is prepended.
    """
    fm_pat = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
    entry = f"compiled_from: {source_rel}"
    m = fm_pat.match(markdown)
    if m:
        inner = m.group(1)
        if "compiled_from:" in inner:
            inner = re.sub(r"compiled_from:.*", entry, inner)
        else:
            inner = inner.rstrip("\n") + f"\n{entry}"
        return f"---\n{inner}\n---\n" + markdown[m.end():]
    return f"---\n{entry}\n---\n\n{markdown}"


def author_raw_to_wiki_markdown(
    raw_text: str,
    source_rel: str,
    *,
    settings: Settings,
    existing_wiki_text: str | None = None,
    known_note_titles: list[str] | None = None,
) -> str:
    """Call the configured chat model to compile one raw document into vault markdown.

    Uses Obsidian OFM instructions from :func:`wiki_llm_system_instructions`.

    When ``existing_wiki_text`` is provided and ``settings.llm_compile_enrich`` is True,
    uses an **enrichment** prompt that merges new source content into the existing article
    rather than rewriting from scratch (Pal-style "enrich, don't replace").

    Injects a ``compiled_from:`` provenance key into the YAML frontmatter of every
    successful output so every wiki note traces back to its raw source.

    On API failure, returns ``raw_text`` unchanged so compile can still proceed.
    """
    if not settings.openai_api_base:
        logger.warning("llm_compile: WIKI_OPENAI_API_BASE unset; skipping author for %s", source_rel)
        return raw_text

    body = _truncate(raw_text, MAX_SOURCE_CHARS)
    known_titles = sorted(t for t in (known_note_titles or []) if t and t != source_rel)
    catalog_hint = ""
    if known_titles:
        catalog_lines = "\n".join(f"- {title}" for title in known_titles[:200])
        catalog_hint = (
            "KNOWN_VAULT_NOTES (use these exact titles when creating wikilinks):\n"
            f"{catalog_lines}\n"
        )
    enrich = (
        settings.llm_compile_enrich
        and existing_wiki_text is not None
        and existing_wiki_text.strip()
    )

    if enrich:
        existing_body = _truncate(existing_wiki_text, MAX_EXISTING_CHARS)  # type: ignore[arg-type]
        task = (
            "You are updating an existing Obsidian wiki article with new source material.\n"
            "EXISTING_ARTICLE: the current wiki page (may already have wikilinks and structure).\n"
            "NEW_SOURCE: new or updated raw content from the same or related source.\n"
            "Rules:\n"
            "- Keep all existing facts that are still accurate.\n"
            "- Merge new facts and details from NEW_SOURCE into the appropriate sections.\n"
            "- Do NOT remove existing wikilinks or backlinks sections.\n"
            "- Do NOT shrink the article — only add or update.\n"
            "- Optimize for a clean, readable Obsidian note, not a transcript dump.\n"
            "- Prefer concise, information-dense prose over filler or repetitive setup sentences.\n"
            "- Keep structure useful: use headings, bullets, and callouts only when they improve scanning.\n"
            "- When referring to another note that exists or plausibly exists in the vault, use an Obsidian [[wikilink]].\n"
            "- Do not leave known or likely in-vault note references as plain text when a [[wikilink]] can be used.\n"
            "- If a note is listed in KNOWN_VAULT_NOTES, use that exact title inside [[...]] rather than inventing a shorter or approximate title.\n"
            "- Link selectively: prefer a small number of high-value wikilinks instead of linking every mention.\n"
            "- Do not create wikilinks for incidental mentions, exhaustive lists, or examples of unrelated topics.\n"
            "- Preserve facts and citations; do not invent sources.\n"
            f"- Raw source path: `{source_rel}`\n"
            "Output only the merged markdown body."
        )
        human_content = (
            f"{catalog_hint}\n"
            f"EXISTING_ARTICLE:\n\n{existing_body}\n\n"
            f"NEW_SOURCE:\n\n{body}"
        )
        logger.info("llm_compile: enriching existing wiki note for %s", source_rel)
    else:
        task = (
            "Compile the SOURCE_DOCUMENT below into a single Obsidian markdown note.\n"
            "- Use YAML frontmatter when helpful (title, tags).\n"
            "- Use headings, lists, and callouts where appropriate.\n"
            "- Produce a clean, readable note for both humans and future AI retrieval.\n"
            "- Prefer concise, information-dense writing over filler, repetition, or generic summary phrases.\n"
            "- Use headings only when they improve navigation; avoid unnecessary sections.\n"
            "- Preserve facts and citations from the source; do not invent sources.\n"
            "- When referring to another note that exists or plausibly exists in the vault, use an Obsidian [[wikilink]].\n"
            "- Do not leave known or likely in-vault note references as plain text when a [[wikilink]] can be used.\n"
            "- If a note is listed in KNOWN_VAULT_NOTES, use that exact title inside [[...]] rather than inventing a shorter or approximate title.\n"
            "- Link selectively: prefer a small number of high-value wikilinks instead of linking every mention.\n"
            "- Do not create wikilinks for incidental mentions, exhaustive lists, or examples of unrelated topics.\n"
            "- Only use plain text when no clear in-vault note target exists.\n"
            f"- Source path (vault-relative raw): `{source_rel}`\n"
            "Output only the markdown body (no surrounding explanation)."
        )
        human_content = f"{catalog_hint}\nSOURCE_DOCUMENT:\n\n{body}"

    system = wiki_llm_system_instructions(task_hint=task, settings=settings)

    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key,
        "temperature": 0.3,
        "request_timeout": settings.llm_request_timeout_sec,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base

    try:
        llm = ChatOpenAI(**kwargs)
        msg = llm.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=human_content),
            ]
        )
        out = msg.content if isinstance(msg.content, str) else str(msg.content)
        out = out.strip()
        if not out:
            return raw_text
        out = _inject_provenance_frontmatter(out, source_rel)
        logger.info(
            "llm_compile %s %s (%s chars out)",
            "enriched" if enrich else "authored",
            source_rel,
            len(out),
        )
        return out
    except Exception as exc:
        err_l = str(exc).lower()
        if "timeout" in err_l or "timed out" in err_l:
            logger.warning(
                "llm_compile failed for %s: %s — using raw text. "
                "Local inference: prefer WIKI_LLM_COMPILE_MAX_WORKERS=1; "
                "raise WIKI_LLM_REQUEST_TIMEOUT_SEC for long notes.",
                source_rel,
                exc,
            )
        else:
            logger.warning("llm_compile failed for %s: %s — using raw text", source_rel, exc)
        return raw_text
