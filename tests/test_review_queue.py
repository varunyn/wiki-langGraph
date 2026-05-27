"""Tests for LLM compile review candidate handling."""

import json
from pathlib import Path

from wiki_langgraph.review_queue import ReviewDecision
from wiki_langgraph.review_queue import assess_candidate
from wiki_langgraph.review_queue import candidate_root
from wiki_langgraph.review_queue import write_candidate


def test_assess_candidate_auto_applies_safe_new_note(tmp_path: Path) -> None:
    decision = assess_candidate(
        mode="risky",
        relpath="new.md",
        generated="---\ncompiled_from: new.md\n---\n\n# New\n\nA useful generated note.",
        existing=None,
    )

    assert decision == ReviewDecision(queue=False, reasons=[])


def test_assess_candidate_queues_existing_note_overwrite() -> None:
    decision = assess_candidate(
        mode="risky",
        relpath="existing.md",
        generated="---\ncompiled_from: existing.md\n---\n\n# Existing\n\nNew version.",
        existing="# Existing\n\nOld version.",
    )

    assert decision.queue is True
    assert "existing_note_overwrite" in decision.reasons


def test_assess_candidate_queues_all_mode() -> None:
    decision = assess_candidate(
        mode="all",
        relpath="new.md",
        generated="---\ncompiled_from: new.md\n---\n\n# New\n\nA useful generated note.",
        existing=None,
    )

    assert decision.queue is True
    assert decision.reasons == ["review_all"]


def test_write_candidate_persists_markdown_and_metadata(tmp_path: Path) -> None:
    root = candidate_root(tmp_path)
    candidate_id = write_candidate(
        root,
        relpath="notes/source.md",
        target_relpath="notes/source.md",
        generated="# Generated\n",
        raw_sha256="a" * 64,
        reasons=["existing_note_overwrite"],
        existing="# Existing\n",
    )

    candidate_dir = root / candidate_id
    assert (candidate_dir / "candidate.md").read_text(encoding="utf-8") == "# Generated\n"
    assert (candidate_dir / "existing.md").read_text(encoding="utf-8") == "# Existing\n"
    metadata = json.loads((candidate_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["id"] == candidate_id
    assert metadata["source_relpath"] == "notes/source.md"
    assert metadata["target_relpath"] == "notes/source.md"
    assert metadata["risk_reasons"] == ["existing_note_overwrite"]
