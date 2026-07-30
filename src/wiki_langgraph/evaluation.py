"""Langfuse experiments and deterministic evaluators for research briefs."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from langfuse import Evaluation

from wiki_langgraph.config import Settings
from wiki_langgraph.observability import langfuse_client
from wiki_langgraph.query import research_query

REQUIRED_SECTIONS = (
    "summary",
    "key findings",
    "source notes",
    "related concepts",
    "open questions",
    "suggested follow-ups",
)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "by",
    "for",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "what",
    "why",
    "with",
}


def load_evaluation_dataset(path: Path) -> dict[str, object]:
    """Load and validate the local research evaluation dataset."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read evaluation dataset {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evaluation dataset JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("evaluation dataset must be a JSON object")
    name = payload.get("name")
    items = payload.get("items")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("evaluation dataset requires a non-empty name")
    if not isinstance(items, list) or not items:
        raise ValueError("evaluation dataset requires a non-empty items list")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each evaluation dataset item must be an object")
        item_id = item.get("id")
        item_input = item.get("input")
        expected = item.get("expectedOutput")
        if not isinstance(item_id, str) or not item_id.strip() or item_id in ids:
            raise ValueError(f"dataset item IDs must be unique and non-empty: {item_id!r}")
        if not isinstance(item_input, dict) or not isinstance(item_input.get("question"), str):
            raise ValueError(f"dataset item {item_id} requires input.question")
        if not isinstance(expected, dict):
            raise ValueError(f"dataset item {item_id} requires expectedOutput")
        if not isinstance(expected.get("themes"), list) or not expected["themes"]:
            raise ValueError(f"dataset item {item_id} requires expectedOutput.themes")
        if not isinstance(expected.get("gaps"), list) or not expected["gaps"]:
            raise ValueError(f"dataset item {item_id} requires expectedOutput.gaps")
        ids.add(item_id)
    return payload


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def _item_value(item: object, name: str) -> object:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _case_parts(item: object) -> tuple[dict[str, object], dict[str, object]]:
    raw_input = _item_value(item, "input")
    raw_expected = _item_value(item, "expected_output")
    if raw_expected is None:
        raw_expected = _item_value(item, "expectedOutput")
    if not isinstance(raw_input, dict) or not isinstance(raw_expected, dict):
        raise ValueError("experiment item must contain input and expected output objects")
    return raw_input, raw_expected


def _output_parts(output: object) -> tuple[str, list[str]]:
    if isinstance(output, Mapping):
        answer = output.get("answer", "")
        sources = output.get("sources", [])
        return str(answer), [str(source) for source in sources] if isinstance(sources, list) else []
    return str(output), []


def _fraction(matches: int, total: int) -> float:
    return round(matches / total, 4) if total else 0.0


def score_research_output(item: object, output: object) -> dict[str, float]:
    """Calculate deterministic research scores in the inclusive range 0..1."""
    item_input, expected = _case_parts(item)
    answer, retrieved_sources = _output_parts(output)
    answer_lower = answer.lower()

    sections = sum(1 for section in REQUIRED_SECTIONS if f"## {section}" in answer_lower)
    structure = _fraction(sections, len(REQUIRED_SECTIONS))

    expected_sources = item_input.get("source_notes", [])
    source_names = {
        Path(str(source)).stem.lower().replace("research/", "")
        for source in retrieved_sources
    }
    source_matches = sum(
        1
        for source in expected_sources
        if Path(str(source)).stem.lower() in source_names
    ) if isinstance(expected_sources, list) else 0
    grounding = _fraction(source_matches, len(expected_sources))
    if "[[" not in answer:
        grounding *= 0.5

    themes = expected.get("themes", [])
    theme_matches = 0
    for theme in themes if isinstance(themes, list) else []:
        theme_tokens = _tokens(str(theme))
        overlap = len(theme_tokens & _tokens(answer)) / len(theme_tokens) if theme_tokens else 0.0
        if overlap >= 0.25:
            theme_matches += 1
    theme_coverage = _fraction(theme_matches, len(themes) if isinstance(themes, list) else 0)

    gaps = expected.get("gaps", [])
    gap_matches = 0
    for gap in gaps if isinstance(gaps, list) else []:
        gap_tokens = _tokens(str(gap))
        overlap = len(gap_tokens & _tokens(answer)) / len(gap_tokens) if gap_tokens else 0.0
        if overlap >= 0.2:
            gap_matches += 1
    uncertainty = _fraction(gap_matches, len(gaps) if isinstance(gaps, list) else 0)

    return {
        "structure": structure,
        "grounding": round(grounding, 4),
        "theme_coverage": theme_coverage,
        "uncertainty": uncertainty,
    }


def _make_evaluator(name: str, score_key: str) -> Callable[..., Evaluation]:
    def evaluator(
        *,
        input: object,
        output: object,
        expected_output: object,
        **_: object,
    ) -> Evaluation:
        item = {"input": input, "expectedOutput": expected_output}
        scores = score_research_output(item, output)
        return Evaluation(
            name=name,
            value=scores[score_key],
            comment=f"Deterministic {name} score: {scores[score_key]:.2f}",
        )

    return evaluator


def research_evaluators() -> list[Callable[..., Evaluation]]:
    """Return the deterministic evaluators used by the first experiment."""
    return [
        _make_evaluator("structure", "structure"),
        _make_evaluator("grounding", "grounding"),
        _make_evaluator("theme_coverage", "theme_coverage"),
        _make_evaluator("uncertainty", "uncertainty"),
    ]


def _research_task(settings: Settings) -> Callable[..., dict[str, object]]:
    def task(*, item: object, **_: object) -> dict[str, object]:
        item_input, _ = _case_parts(item)
        question = item_input["question"]
        if not isinstance(question, str):
            raise ValueError("experiment item input.question must be a string")
        result = research_query(question, settings=settings, top_k=8)
        return {
            "answer": result.answer,
            "sources": [source.relpath for source in result.sources],
        }

    return task


def run_research_experiment(
    *,
    settings: Settings,
    dataset_path: Path,
    name: str | None = None,
    max_concurrency: int = 1,
    hosted: bool = True,
) -> object:
    """Run the research dataset through Langfuse's v4 experiment runner."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1")
    client = langfuse_client(settings)
    if client is None:
        raise RuntimeError("Langfuse is not configured; enable tracing and set both project keys")
    payload = load_evaluation_dataset(dataset_path)
    raw_items = payload["items"]
    if not isinstance(raw_items, list):
        raise ValueError("evaluation dataset items must be a list")
    data: list[dict[str, object]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("evaluation dataset items must be objects")
        data.append(
            {
                "input": raw_item["input"],
                "expected_output": raw_item["expectedOutput"],
                "metadata": raw_item.get("metadata", {}),
            }
        )
    dataset_name = str(payload["name"])
    experiment_name = name or dataset_name
    description = str(payload.get("description", ""))
    metadata = payload.get("metadata", {})
    experiment_metadata = {
        key: str(value)
        for key, value in metadata.items()
    } if isinstance(metadata, dict) else {}
    task = _research_task(settings)
    evaluators = research_evaluators()
    if hosted:
        try:
            dataset = client.get_dataset(dataset_name)
        except Exception as exc:
            raise RuntimeError(
                f"could not fetch hosted Langfuse dataset {dataset_name!r}: {exc}"
            ) from exc
        return dataset.run_experiment(
            name=experiment_name,
            description=description,
            task=task,
            evaluators=evaluators,
            max_concurrency=max_concurrency,
            metadata=experiment_metadata,
        )
    return client.run_experiment(
        name=experiment_name,
        description=description,
        data=data,
        task=task,
        evaluators=evaluators,
        max_concurrency=max_concurrency,
        metadata=experiment_metadata,
    )
