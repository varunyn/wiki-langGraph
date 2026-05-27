"""Question answering over the compiled wiki, with optional saved query notes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from wiki_langgraph.config import Settings
from wiki_langgraph.linking import wikilink_display_name
from wiki_langgraph.llm_author import _message_text

MAX_EXCERPT_CHARS = 2_400


@dataclass(frozen=True)
class QuerySource:
    """One retrieved wiki note used as query context."""

    relpath: str
    title: str
    excerpt: str
    score: int


@dataclass(frozen=True)
class QueryResult:
    """Answer plus retrieved sources."""

    question: str
    answer: str
    sources: list[QuerySource]


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9]+", text.lower()) if len(t) > 2]


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip()
    return text


def _excerpt(text: str) -> str:
    body = _strip_frontmatter(text).strip()
    if len(body) <= MAX_EXCERPT_CHARS:
        return body
    return body[:MAX_EXCERPT_CHARS].rsplit("\n", 1)[0].strip()


def _score(query_tokens: list[str], relpath: str, text: str) -> int:
    haystack_title = wikilink_display_name(relpath).lower()
    haystack = text.lower()
    score = 0
    for token in query_tokens:
        if token in haystack_title:
            score += 8
        score += haystack.count(token)
    return score


def search_wiki_context(question: str, *, settings: Settings, top_k: int = 5) -> list[QuerySource]:
    """Return the most relevant compiled wiki notes using a local lexical scorer."""
    wiki = settings.wiki_dir()
    query_tokens = _tokens(question)
    if not wiki.is_dir() or not query_tokens:
        return []

    results: list[QuerySource] = []
    for path in sorted(wiki.rglob("*.md")):
        rel = path.relative_to(wiki).as_posix()
        if path.name.lower() == "index.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        score = _score(query_tokens, rel, text)
        if score <= 0:
            continue
        results.append(
            QuerySource(
                relpath=rel,
                title=wikilink_display_name(rel),
                excerpt=_excerpt(text),
                score=score,
            )
        )
    results.sort(key=lambda item: (-item.score, item.relpath.lower()))
    return results[:top_k]


def _answer_prompt(question: str, sources: list[QuerySource]) -> list[object]:
    context = "\n\n".join(
        f"Source: {source.relpath}\nTitle: {source.title}\nExcerpt:\n{source.excerpt}"
        for source in sources
    )
    system = (
        "Answer questions using the supplied Obsidian wiki context. "
        "Use concise, concrete prose. Include wikilinks to relevant source notes using exact titles. "
        "If the context is insufficient, say what is missing."
    )
    human = f"QUESTION:\n{question}\n\nWIKI_CONTEXT:\n{context}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def _research_prompt(question: str, sources: list[QuerySource]) -> list[object]:
    context = "\n\n".join(
        f"Source: {source.relpath}\nTitle: {source.title}\nExcerpt:\n{source.excerpt}"
        for source in sources
    )
    system = (
        "Create research briefs from supplied Obsidian wiki context. "
        "Synthesize across notes instead of answering narrowly. "
        "Use wikilinks with exact source-note titles for concrete claims. "
        "Separate evidence-backed findings from gaps or open questions. "
        "If the context is insufficient, make the limitation explicit."
    )
    human = (
        f"RESEARCH_QUESTION:\n{question}\n\n"
        f"WIKI_CONTEXT:\n{context}\n\n"
        "Write a markdown Research Brief with these sections:\n"
        "# Research Brief\n"
        "## Summary\n"
        "## Key Findings\n"
        "## Source Notes\n"
        "## Related Concepts\n"
        "## Open Questions\n"
        "## Suggested Follow-ups\n"
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def answer_query(question: str, *, settings: Settings, top_k: int = 5) -> QueryResult:
    """Retrieve wiki context and answer the question with the configured chat model."""
    sources = search_wiki_context(question, settings=settings, top_k=top_k)
    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key,
        "temperature": 0.2,
        "request_timeout": settings.llm_request_timeout_sec,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base
    llm = ChatOpenAI(**kwargs)
    msg = llm.invoke(_answer_prompt(question, sources))
    answer = _message_text(msg).strip()
    return QueryResult(question=question, answer=answer, sources=sources)


def research_query(question: str, *, settings: Settings, top_k: int = 8) -> QueryResult:
    """Retrieve broader wiki context and synthesize a structured research brief."""
    sources = search_wiki_context(question, settings=settings, top_k=top_k)
    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key,
        "temperature": 0.2,
        "request_timeout": settings.llm_request_timeout_sec,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base
    llm = ChatOpenAI(**kwargs)
    msg = llm.invoke(_research_prompt(question, sources))
    brief = _message_text(msg).strip()
    return QueryResult(question=question, answer=brief, sources=sources)


def _slug_title(question: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", question).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:80].strip() or "Saved Query")


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem} {i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find unique path for {path}")


def save_query_answer(
    *,
    question: str,
    answer: str,
    source_relpaths: list[str],
    settings: Settings,
) -> Path:
    """Save a query answer as a raw note under ``Queries/``."""
    title = _slug_title(question)
    path = _unique_path(settings.raw_dir() / "Queries" / f"{title}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_lines = "\n".join(f"- [[{wikilink_display_name(rel)}]]" for rel in source_relpaths)
    text = (
        "---\n"
        f"title: {question}\n"
        "tags:\n"
        "  - saved-query\n"
        "  - ai\n"
        f"source_question: {question}\n"
        f"created: {created}\n"
        "---\n\n"
        f"# {question}\n\n"
        f"> Source question: {question}\n\n"
        f"{answer.strip()}\n\n"
        "## Sources\n\n"
        f"{source_lines or '_No matching wiki sources were retrieved._'}\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def save_research_brief(
    *,
    question: str,
    brief: str,
    source_relpaths: list[str],
    settings: Settings,
) -> Path:
    """Save a research brief as a raw note under ``Research/``."""
    title = _slug_title(question)
    path = _unique_path(settings.raw_dir() / "Research" / f"{title}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_lines = "\n".join(f"- [[{wikilink_display_name(rel)}]]" for rel in source_relpaths)
    text = (
        "---\n"
        f"title: {question}\n"
        "tags:\n"
        "  - research\n"
        "  - ai\n"
        f"source_question: {question}\n"
        f"created: {created}\n"
        "---\n\n"
        f"> Source question: {question}\n\n"
        f"{brief.strip()}\n\n"
        "## Sources\n\n"
        f"{source_lines or '_No matching wiki sources were retrieved._'}\n"
    )
    path.write_text(text, encoding="utf-8")
    return path
