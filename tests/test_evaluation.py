"""Tests for research evaluation dataset scoring."""

from pathlib import Path

from wiki_langgraph.evaluation import load_evaluation_dataset, score_research_output


def _case() -> dict[str, object]:
    return {
        "id": "case-1",
        "input": {
            "question": "How should we evaluate research?",
            "source_notes": ["Research Note One", "Research Note Two"],
        },
        "expectedOutput": {
            "themes": ["source grounding", "theme coverage"],
            "gaps": ["thresholds are not finalized"],
        },
    }


def test_score_research_output_rewards_grounded_structured_answer() -> None:
    item = _case()
    answer = """# Research Brief

## Summary
Use source grounding and theme coverage.

## Key Findings
Thresholds are not finalized.

## Source Notes
[[Research Note One]] and [[Research Note Two]]

## Related Concepts
Grounding.

## Open Questions
Thresholds are not finalized.

## Suggested Follow-ups
Set thresholds.
"""
    scores = score_research_output(
        item,
        {"answer": answer, "sources": ["Research/Research Note One.md", "Research/Research Note Two.md"]},
    )

    assert scores["structure"] == 1.0
    assert scores["grounding"] == 1.0
    assert scores["theme_coverage"] == 1.0
    assert scores["uncertainty"] == 1.0


def test_score_research_output_penalizes_missing_sections_and_sources() -> None:
    scores = score_research_output(
        _case(),
        {"answer": "## Summary\nA vague answer.", "sources": []},
    )

    assert scores["structure"] < 1.0
    assert scores["grounding"] == 0.0
    assert scores["theme_coverage"] < 1.0


def test_load_evaluation_dataset_validates_repository_dataset() -> None:
    payload = load_evaluation_dataset(Path("evals/research_dataset.json"))

    assert payload["name"] == "wiki-langgraph-research-v1"
    assert len(payload["items"]) == 5  # type: ignore[arg-type]
