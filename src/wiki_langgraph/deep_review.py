"""Opt-in DeepAgent review of queued candidates without direct vault writes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from wiki_langgraph.config import Settings
from wiki_langgraph.deep_agent import create_wiki_deep_agent
from wiki_langgraph.review_queue import candidate_root


@dataclass(frozen=True)
class DeepReviewResult:
    """A read-only DeepAgent review report."""

    candidate_ids: list[str]
    report: str


def _message_text(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("text")
        )
    return str(content)


def _candidate_ids(settings: Settings, requested: list[str] | None, limit: int) -> list[str]:
    root = candidate_root(settings.project_root)
    if requested:
        return [candidate_id for candidate_id in requested if (root / candidate_id / "metadata.json").is_file()][:limit]
    if not root.is_dir():
        return []
    return [
        path.name
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "metadata.json").is_file()
    ][:limit]


def review_candidates(
    settings: Settings,
    *,
    candidate_ids: list[str] | None = None,
    limit: int = 3,
) -> DeepReviewResult:
    """Ask a read-only DeepAgent to review up to ``limit`` queued candidates."""
    selected = _candidate_ids(settings, candidate_ids, limit)
    if not selected:
        return DeepReviewResult([], "no pending review candidates")

    root = candidate_root(settings.project_root)
    metadata: list[dict[str, object]] = []
    for candidate_id in selected:
        metadata.append(json.loads((root / candidate_id / "metadata.json").read_text(encoding="utf-8")))
    prompt = (
        "Review the queued wiki candidates listed below. Read each candidate.md and, when present, "
        "existing.md. Do not edit, approve, reject, or write any files. Return a concise report for "
        "a human reviewer with one recommendation per candidate: approve, revise, or reject, plus "
        "the key reason.\n\n"
        f"Candidates:\n{json.dumps(metadata, indent=2, sort_keys=True)}"
    )
    read_paths = ["/AGENTS.md", "/skills/**"]
    read_paths.extend(
        f"/data/.wiki-langgraph/candidates/{candidate_id}/**" for candidate_id in selected
    )
    agent = create_wiki_deep_agent(
        settings=settings,
        read_only=True,
        read_paths=read_paths,
        system_prompt="You are a cautious wiki candidate reviewer. Never modify the filesystem.",
    )
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    messages = result.get("messages", []) if isinstance(result, dict) else []
    report = _message_text(messages[-1]) if messages else str(result)
    return DeepReviewResult(selected, report.strip())
