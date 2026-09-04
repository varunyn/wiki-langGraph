"""Tests for research evaluation dataset scoring."""

from pathlib import Path
from types import SimpleNamespace

from wiki_langgraph.config import Settings
from wiki_langgraph.evaluation import (
    _knowledge_gap_task,
    _parse_dataset_version,
    load_evaluation_dataset,
    run_knowledge_gap_experiment,
    run_research_experiment,
    score_knowledge_gap_output,
    score_research_output,
)


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


def test_load_evaluation_dataset_validates_new_versioned_datasets() -> None:
    research = load_evaluation_dataset(Path("evals/research_dataset_v2.json"))
    gaps = load_evaluation_dataset(Path("evals/knowledge_gap_dataset.json"))

    assert research["name"] == "wiki-langgraph-research-v2"
    assert len(research["items"]) == 6  # type: ignore[arg-type]
    assert gaps["name"] == "wiki-langgraph-knowledge-gap-v1"
    assert len(gaps["items"]) == 6  # type: ignore[arg-type]
    assert gaps["metadata"]["status"] == "draft"  # type: ignore[index]
    assert all("scenario" not in item["input"] for item in gaps["items"])  # type: ignore[union-attr]


def test_score_knowledge_gap_output_checks_coverage_safety_and_bounds() -> None:
    item = {
        "input": {"scenario": "review", "fixture": "fixture"},
        "expectedOutput": {
            "categories": ["possible_duplicate", "weak_connection"],
            "reviewed_paths": ["Alpha.md", "Beta.md"],
            "partial": True,
            "max_findings": 3,
        },
    }
    scores = score_knowledge_gap_output(
        item,
        {
            "categories": ["possible_duplicate", "possible_conflict"],
            "reviewed_paths": ["Alpha.md", "Beta.md"],
            "partial": True,
            "finding_count": 2,
            "read_only": True,
        },
    )

    assert scores == {
        "category_precision": 0.5,
        "category_recall": 0.5,
        "category_f1": 0.5,
        "review_scope": 1.0,
        "partial_disclosure": 1.0,
        "read_only": 1.0,
        "finding_bound": 1.0,
    }


def test_parse_dataset_version_requires_timezone() -> None:
    parsed = _parse_dataset_version("2026-09-03T12:30:00Z")

    assert parsed is not None
    assert parsed.utcoffset() is not None

    try:
        _parse_dataset_version("2026-09-03T12:30:00")
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("expected a timezone validation error")


def test_hosted_research_experiment_selects_exact_dataset_version(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class Dataset:
        def run_experiment(self, **kwargs: object) -> object:
            captured["run"] = kwargs
            return object()

    class Client:
        def get_dataset(self, name: str, *, version: object) -> Dataset:
            captured["name"] = name
            captured["version"] = version
            return Dataset()

    monkeypatch.setattr("wiki_langgraph.evaluation.langfuse_client", lambda _settings: Client())
    settings = Settings(project_root=Path.cwd())

    run_research_experiment(
        settings=settings,
        dataset_path=Path("evals/research_dataset.json"),
        dataset_version="2026-09-03T12:30:00Z",
    )

    assert captured["name"] == "wiki-langgraph-research-v1"
    assert captured["version"].isoformat() == "2026-09-03T12:30:00+00:00"  # type: ignore[union-attr]


def test_knowledge_gap_experiment_defaults_to_local_data(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class Client:
        def get_dataset(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("default knowledge-gap run must not fetch hosted data")

        def run_experiment(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return object()

    monkeypatch.setattr("wiki_langgraph.evaluation.langfuse_client", lambda _settings: Client())

    run_knowledge_gap_experiment(
        settings=Settings(project_root=Path.cwd()),
        dataset_path=Path("evals/knowledge_gap_dataset.json"),
    )

    assert len(captured["data"]) == 6  # type: ignore[arg-type]


def test_knowledge_gap_task_uses_isolated_fixture_and_detects_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    fixture = tmp_path / "fixture"
    (fixture / "raw").mkdir(parents=True)
    (fixture / "wiki").mkdir()
    (fixture / "raw" / "Alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (fixture / "wiki" / "Alpha.md").write_text("# Alpha\n", encoding="utf-8")
    settings = Settings(
        project_root=tmp_path,
        data_raw_dir=tmp_path / "unused-raw",
        data_wiki_dir=tmp_path / "unused-wiki",
        openai_api_base="http://localhost/v1",
        llm_model="test",
    )

    def fake_review(fixture_settings, *, scope, limit):  # noqa: ANN001
        assert fixture_settings.project_root != tmp_path
        assert scope is None
        assert limit == 2
        (fixture_settings.raw_dir() / "Alpha.md").write_text("changed", encoding="utf-8")
        return SimpleNamespace(
            findings=[SimpleNamespace(category="weak_connection")],
            reviewed_paths=["Alpha.md"],
            partial=False,
            omitted_count=0,
        )

    monkeypatch.setattr("wiki_langgraph.evaluation.review_knowledge_gaps", fake_review)
    task = _knowledge_gap_task(settings)
    output = task(
        item={
            "input": {"fixture": "fixture", "limit": 2},
            "expectedOutput": {
                "categories": ["weak_connection"],
                "reviewed_paths": ["Alpha.md"],
                "partial": False,
                "max_findings": 2,
            },
        }
    )

    assert output["read_only"] is False
    assert output["categories"] == ["weak_connection"]
    assert (fixture / "raw" / "Alpha.md").read_text(encoding="utf-8") == "# Alpha\n"


def test_knowledge_gap_fixture_selection_matches_dataset(monkeypatch) -> None:  # noqa: ANN001
    payload = load_evaluation_dataset(Path("evals/knowledge_gap_dataset.json"))

    class Agent:
        def invoke(self, payload: object) -> dict[str, object]:
            return {
                "structured_response": {
                    "summary": "fixture audit",
                    "findings": [],
                    "insufficient_evidence": [],
                },
                "messages": [],
            }

    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: Agent(),
    )
    task = _knowledge_gap_task(
        Settings(
            project_root=Path.cwd(),
            data_raw_dir=Path("data/raw"),
            data_wiki_dir=Path("data/wiki"),
            openai_api_base="http://localhost/v1",
            llm_model="test",
        )
    )

    for item in payload["items"]:  # type: ignore[union-attr]
        output = task(item=item)
        expected = item["expectedOutput"]
        assert set(output["reviewed_paths"]) == set(expected["reviewed_paths"])
        assert output["partial"] is expected["partial"]
        assert output["read_only"] is True
