"""Tests for the opt-in, read-only DeepAgent review boundary."""

import json
from pathlib import Path
from types import SimpleNamespace

from wiki_langgraph.config import Settings
from wiki_langgraph.deep_review import review_candidates


def test_review_candidates_skips_deep_agent_when_queue_is_empty(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    settings = Settings(project_root=tmp_path)
    monkeypatch.setattr(
        "wiki_langgraph.deep_review.create_wiki_deep_agent",
        lambda **_: (_ for _ in ()).throw(AssertionError("empty queue must not invoke DeepAgent")),
    )

    result = review_candidates(settings)

    assert result.candidate_ids == []
    assert result.report == "no pending review candidates"


def test_review_candidates_invokes_read_only_agent_for_selected_candidate(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    settings = Settings(project_root=tmp_path)
    candidate = tmp_path / "data" / ".wiki-langgraph" / "candidates" / "candidate-1"
    candidate.mkdir(parents=True)
    (candidate / "candidate.md").write_text("# Candidate\n", encoding="utf-8")
    (candidate / "metadata.json").write_text(
        json.dumps({"id": "candidate-1", "source_relpath": "note.md"}),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeAgent:
        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"messages": [SimpleNamespace(content="approve: candidate is safe")]}

    def fake_create(**kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr("wiki_langgraph.deep_review.create_wiki_deep_agent", fake_create)

    result = review_candidates(settings, candidate_ids=["candidate-1"])

    assert result.candidate_ids == ["candidate-1"]
    assert result.report == "approve: candidate is safe"
    assert captured["read_only"] is True
    assert "/data/.wiki-langgraph/candidates/candidate-1/**" in captured["read_paths"]
    assert "candidate.md" in str(captured["payload"])
