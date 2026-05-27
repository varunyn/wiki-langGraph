"""Review queue for risky LLM-authored wiki candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wiki_langgraph.linking import extract_wikilink_targets
from wiki_langgraph.manifest import str_sha256

ReviewMode = str


@dataclass(frozen=True)
class ReviewDecision:
    """Whether a generated note should be queued before writing."""

    queue: bool
    reasons: list[str]


def candidate_root(project_root: Path) -> Path:
    """Default candidate queue root."""
    return project_root / "data" / ".wiki-langgraph" / "candidates"


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _has_compiled_from(text: str, relpath: str) -> bool:
    return f"compiled_from: {relpath}" in text


def assess_candidate(
    *,
    mode: ReviewMode,
    relpath: str,
    generated: str,
    existing: str | None,
) -> ReviewDecision:
    """Classify generated markdown for review routing."""
    normalized_mode = mode if mode in {"off", "risky", "all"} else "off"
    if normalized_mode == "off":
        return ReviewDecision(queue=False, reasons=[])
    if normalized_mode == "all":
        return ReviewDecision(queue=True, reasons=["review_all"])

    reasons: list[str] = []
    generated_words = _word_count(generated)
    if not generated.strip():
        reasons.append("empty_output")
    elif generated_words < 8:
        reasons.append("too_short")
    if not _has_compiled_from(generated, relpath):
        reasons.append("missing_compiled_from")

    if existing is not None and existing.strip():
        reasons.append("existing_note_overwrite")
        existing_words = _word_count(existing)
        if existing_words and generated_words < max(8, int(existing_words * 0.5)):
            reasons.append("large_shrink")
        old_links = extract_wikilink_targets(existing)
        new_links = extract_wikilink_targets(generated)
        removed = old_links - new_links
        added = new_links - old_links
        if len(removed) + len(added) >= 5:
            reasons.append("wikilink_churn")

    return ReviewDecision(queue=bool(reasons), reasons=reasons)


def _safe_candidate_id(relpath: str, generated: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", relpath).strip("-").replace("/", "-")
    stem = stem[:80] or "candidate"
    return f"{stem}-{str_sha256(generated)[:12]}"


def write_candidate(
    root: Path,
    *,
    relpath: str,
    target_relpath: str,
    generated: str,
    raw_sha256: str,
    reasons: list[str],
    existing: str | None = None,
) -> str:
    """Persist one queued candidate and return its id."""
    candidate_id = _safe_candidate_id(relpath, generated)
    dest = root / candidate_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "candidate.md").write_text(generated, encoding="utf-8")
    if existing is not None:
        (dest / "existing.md").write_text(existing, encoding="utf-8")
    metadata = {
        "id": candidate_id,
        "source_relpath": relpath,
        "target_relpath": target_relpath,
        "raw_sha256": raw_sha256,
        "risk_reasons": reasons,
        "generated_word_count": _word_count(generated),
        "existing_word_count": _word_count(existing or ""),
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    (dest / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate_id
