"""Merge wiki-langgraph graph metadata into YAML frontmatter (Obsidian properties)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import yaml

logger = logging.getLogger(__name__)

# Top-level keys only — Obsidian's Properties UI edits scalars per property; nested YAML
# maps under one key often show as an unparsed blob. See https://obsidian.md/help/properties
WG_VERSION = "wiki_langgraph_version"
WG_COMPILED = "wiki_langgraph_compiled"
WG_KIND = "wiki_langgraph_kind"
NOTE_CREATED = "created"
NOTE_MODIFIED = "modified"

INDEX_KIND_VALUE = "index"


@dataclass(frozen=True)
class WikiGraphFrontmatterStats:
    """Minimal pipeline provenance: when this note was last compiled."""

    compiled_at_iso: str
    created_at_iso: str | None = None


def _normalize_tags(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [str(raw).strip()]


def _strip_legacy_pipeline_tags(tags: list[str]) -> list[str]:
    """Remove auto-injected ``wiki-langgraph/...`` tags from older compiles."""
    return [t for t in tags if not t.startswith("wiki-langgraph/")]


def _strip_legacy_nested_wiki_langgraph(data: dict[str, object]) -> None:
    """Remove nested ``wiki_langgraph:`` block from older compiles."""
    if "wiki_langgraph" in data:
        del data["wiki_langgraph"]


def _flat_wiki_graph_properties(stats: WikiGraphFrontmatterStats) -> dict[str, object]:
    flat: dict[str, object] = {
        WG_VERSION: 1,
        WG_COMPILED: stats.compiled_at_iso,
        NOTE_MODIFIED: stats.compiled_at_iso,
    }
    if stats.created_at_iso is not None:
        flat[NOTE_CREATED] = stats.created_at_iso
    return flat


def _apply_managed_wiki_graph_keys(data: dict[str, object], flat: dict[str, object]) -> None:
    """Drop prior flat ``wiki_langgraph_*`` keys, remove legacy nested block, set new values."""
    _strip_legacy_nested_wiki_langgraph(data)
    drop = [k for k in data if k.startswith("wiki_langgraph_")]
    for k in drop:
        del data[k]
    data.update(flat)


def _quote_timestamp_like_scalars(dumped: str) -> str:
    dumped = re.sub(
        rf"^({WG_COMPILED}|{NOTE_CREATED}|{NOTE_MODIFIED}):\s*(.+)$",
        lambda m: f"{m.group(1)}: '{m.group(2).strip().strip("\'")}'",
        dumped,
        flags=re.MULTILINE,
    )
    return dumped


def _iso_like_string(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def merge_wiki_graph_frontmatter(markdown: str, *, stats: WikiGraphFrontmatterStats) -> str:
    """Insert or merge flat ``wiki_langgraph_version`` / ``wiki_langgraph_compiled``.

    Link counts are **not** stored here — they duplicate the wikilink / See also / Backlinks
    sections in the note body. Preserves user ``tags``; strips legacy pipeline tags.

    Managed keys are **replaced** on each compile. If YAML parsing fails, returns
    ``markdown`` unchanged and logs a warning.
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown, flags=re.DOTALL)
    if m:
        inner = m.group(1)
        rest = markdown[m.end() :]
        try:
            data = yaml.safe_load(inner)
        except yaml.YAMLError as e:
            logger.warning("wiki_langgraph: skip frontmatter merge (YAML error): %s", e)
            return markdown
        if not isinstance(data, dict):
            data = {}
        frontmatter = cast(dict[str, object], data)
        cleaned = _strip_legacy_pipeline_tags(_normalize_tags(frontmatter.get("tags")))
        if cleaned:
            frontmatter["tags"] = cleaned
        elif "tags" in frontmatter:
            del frontmatter["tags"]
        created_value = frontmatter.get(NOTE_CREATED)
        if created_value is not None:
            stats = WikiGraphFrontmatterStats(
                compiled_at_iso=stats.compiled_at_iso,
                created_at_iso=_iso_like_string(created_value),
            )
        _apply_managed_wiki_graph_keys(frontmatter, _flat_wiki_graph_properties(stats))
        dumped = yaml.dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )
        dumped = _quote_timestamp_like_scalars(dumped)
        if not dumped.endswith("\n"):
            dumped += "\n"
        return f"---\n{dumped}---\n{rest}"

    data = dict(_flat_wiki_graph_properties(stats))
    dumped = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    dumped = _quote_timestamp_like_scalars(dumped)
    if not dumped.endswith("\n"):
        dumped += "\n"
    return f"---\n{dumped}---\n{markdown.lstrip()}"


def utc_now_iso() -> str:
    """UTC ``wiki_langgraph_compiled`` timestamp for frontmatter."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
