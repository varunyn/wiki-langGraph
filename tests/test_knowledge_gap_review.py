"""Focused tests for bounded knowledge-gap review orchestration."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from wiki_langgraph.config import Settings
from wiki_langgraph.knowledge_gap_review import review_knowledge_gaps


def _settings(tmp_path: Path) -> Settings:
    raw, wiki = tmp_path / "raw", tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    return Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        openai_api_base="http://localhost/v1",
        llm_model="test",
    )


def _write_pair(settings: Settings, rel: str, text: str = "# Note\n\n[[Neighbor]]") -> None:
    raw_path = settings.raw_dir() / rel
    wiki_path = settings.wiki_dir() / rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")
    wiki_path.write_text(text, encoding="utf-8")


def _tool_trace(*paths: str) -> list[object]:
    calls = [
        {"name": "read_file", "args": {"file_path": path}, "id": str(index)}
        for index, path in enumerate(paths, start=1)
    ]
    messages: list[object] = [SimpleNamespace(tool_calls=calls)]
    messages.extend(
        SimpleNamespace(
            type="tool",
            name="read_file",
            tool_call_id=str(index),
            content="# inspected",
            status="success",
        )
        for index in range(1, len(paths) + 1)
    )
    return messages


def _agent_result(
    *,
    findings: list[dict[str, object]] | None = None,
    inspected: tuple[str, ...] = (),
    summary: str = "reviewed",
) -> dict[str, object]:
    return {
        "structured_response": {
            "summary": summary,
            "findings": findings or [],
            "insufficient_evidence": [],
        },
        "messages": _tool_trace(*inspected),
    }


def _fake_agent(result: object):  # noqa: ANN202
    class Agent:
        def invoke(self, payload: object) -> object:
            return result

    return Agent()


def test_empty_valid_scope_is_read_only_and_skips_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    (settings.raw_dir() / "empty").mkdir()
    monkeypatch.setattr("wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent", lambda **_: pytest.fail("agent called"))
    result = review_knowledge_gaps(settings, scope="empty")
    assert result.summary == "no reviewable notes"
    assert "no reviewable notes" in result.report


def test_scope_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="relative POSIX"):
        review_knowledge_gaps(settings, scope="../secret")
    outside = tmp_path / "outside"
    outside.mkdir()
    (settings.raw_dir() / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        review_knowledge_gaps(settings, scope="link")


def test_nonexistent_scope_is_invalid_not_empty(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(ValueError, match="scope does not exist"):
        review_knowledge_gaps(settings, scope="missing")


def test_existing_non_markdown_file_is_not_a_valid_scope(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.wiki_dir() / "notes.txt").write_text("not markdown", encoding="utf-8")

    with pytest.raises(ValueError, match="scope does not exist"):
        review_knowledge_gaps(settings, scope="notes.txt")


def test_raw_wiki_prefix_mapping_and_deterministic_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    (settings.raw_dir() / "wiki").mkdir()
    (settings.raw_dir() / "wiki" / "topic.md").write_text("# Topic\n[[other]]", encoding="utf-8")
    (settings.wiki_dir() / "topic.md").write_text("# Topic", encoding="utf-8")
    (settings.raw_dir() / "other.md").write_text("# Other", encoding="utf-8")
    (settings.wiki_dir() / "other.md").write_text("# Other", encoding="utf-8")
    captured: dict[str, object] = {}
    class Agent:
        def invoke(self, payload: object) -> dict[str, object]:
            captured["payload"] = payload
            return {"structured_response": {"summary": "ok", "findings": [], "insufficient_evidence": []}, "messages": []}
    monkeypatch.setattr("wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent", lambda **kwargs: (captured.update(kwargs) or Agent()))
    result = review_knowledge_gaps(settings, scope="topic.md", limit=1)
    assert result.reviewed_paths == ["topic.md"]
    assert result.omitted_count == 0
    assert "/raw/wiki/topic.md" in result.read_allowlist


def test_selection_prioritizes_missing_counterpart_then_outgoing_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md", "# A\n\n[[B]] [[C]]")
    _write_pair(settings, "b.md", "# B\n\n[[A]]")
    (settings.raw_dir() / "c.md").write_text("# C\n\n[[A]]", encoding="utf-8")
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: _fake_agent(_agent_result()),
    )

    result = review_knowledge_gaps(settings, limit=2)

    assert result.reviewed_paths == ["c.md", "a.md"]
    assert result.partial is True
    assert result.omitted_count == 1
    assert "narrow the scope" in result.report


def test_preanalysis_includes_title_and_resolved_authored_relationships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md", "---\ntitle: Alpha Title\n---\n\n[[B]]")
    _write_pair(settings, "b.md", "# Beta\n\n[[A]]")
    captured: dict[str, object] = {}

    class Agent:
        def invoke(self, payload: object) -> object:
            captured["payload"] = payload
            return _agent_result()

    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: Agent(),
    )

    review_knowledge_gaps(settings)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    messages = payload["messages"]
    assert isinstance(messages, list)
    prompt = messages[0]["content"]
    assert isinstance(prompt, str)
    assert '"title": "Alpha Title"' in prompt
    assert '"outgoing_authored_links": [\n      "b.md"' in prompt
    assert '"incoming_authored_links": [\n      "b.md"' in prompt


def test_malformed_and_uninspected_evidence_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    (settings.raw_dir() / "a.md").write_text("# A", encoding="utf-8")
    (settings.wiki_dir() / "a.md").write_text("# A", encoding="utf-8")
    class Agent:
        def invoke(self, payload: object) -> dict[str, object]:
            return {"structured_response": {"summary": "x", "findings": [{"category": "missing_concept", "priority": "high", "confidence": .5, "affected_paths": ["a.md"], "evidence": [{"path": "/data/raw/a.md", "observation": "x"}], "why_it_matters": "x", "recommendation": "x"}], "insufficient_evidence": []}, "messages": []}
    monkeypatch.setattr("wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent", lambda **_: Agent())
    with pytest.raises(ValueError, match="inspected"):
        review_knowledge_gaps(settings)


def test_duplicate_requires_two_paths_and_uncertainty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    for name in ("a.md", "b.md"):
        (settings.raw_dir() / name).write_text(f"# {name}", encoding="utf-8")
        (settings.wiki_dir() / name).write_text(f"# {name}", encoding="utf-8")
    class Agent:
        def invoke(self, payload: object) -> dict[str, object]:
            return {"structured_response": {"summary": "x", "findings": [{"category": "possible_duplicate", "priority": "low", "confidence": .5, "affected_paths": ["a.md", "b.md"], "evidence": [{"path": "/raw/a.md", "observation": "x"}, {"path": "/raw/b.md", "observation": "y"}], "why_it_matters": "x", "recommendation": "x"}], "insufficient_evidence": []}, "messages": [{"tool_calls": [{"name": "read_file", "args": {"file_path": "/raw/a.md"}, "id": "1"}, {"name": "read_file", "args": {"file_path": "/raw/b.md"}, "id": "2"}]}, {"role": "tool", "tool_call_id": "1", "content": "# A"}, {"role": "tool", "tool_call_id": "2", "content": "# B"}]}
    monkeypatch.setattr("wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent", lambda **_: Agent())
    with pytest.raises(ValueError, match="uncertainty"):
        review_knowledge_gaps(settings)


@pytest.mark.parametrize(
    "category",
    ["missing_concept", "missing_overview", "weak_connection", "source_coverage_gap"],
)
def test_each_single_note_finding_category_is_validated_and_rendered(
    category: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md")
    finding = {
        "category": category,
        "priority": "medium",
        "confidence": 0.75,
        "affected_paths": ["a.md"],
        "evidence": [{"path": "/raw/a.md", "observation": "Observed detail"}],
        "why_it_matters": "It leaves the topic incomplete.",
        "recommendation": "Review the concept.",
        "uncertainty": None,
    }
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: _fake_agent(
            _agent_result(findings=[finding], inspected=("/raw/a.md",))
        ),
    )

    result = review_knowledge_gaps(settings)

    assert result.findings[0].category == category
    assert f"### {category}" in result.render_markdown()


@pytest.mark.parametrize("category", ["possible_duplicate", "possible_conflict"])
def test_comparison_categories_require_and_preserve_uncertainty(
    category: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md")
    _write_pair(settings, "b.md")
    finding = {
        "category": category,
        "priority": "low",
        "confidence": 0.6,
        "affected_paths": ["a.md", "b.md"],
        "evidence": [
            {"path": "/raw/a.md", "observation": "First framing"},
            {"path": "/raw/b.md", "observation": "Second framing"},
        ],
        "why_it_matters": "The concepts may overlap.",
        "recommendation": "Compare them manually.",
        "uncertainty": "The terminology may be intentionally distinct.",
    }
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: _fake_agent(
            _agent_result(
                findings=[finding],
                inspected=("/raw/a.md", "/raw/b.md"),
            )
        ),
    )

    result = review_knowledge_gaps(settings)

    assert "Uncertainty: The terminology may be intentionally distinct." in result.report


def test_failed_tool_result_does_not_count_as_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md")
    finding = {
        "category": "missing_concept",
        "priority": "high",
        "confidence": 0.8,
        "affected_paths": ["a.md"],
        "evidence": [{"path": "/raw/a.md", "observation": "Claimed"}],
        "why_it_matters": "Incomplete.",
        "recommendation": "Investigate.",
        "uncertainty": None,
    }
    result = _agent_result(findings=[finding])
    result["messages"] = [
        SimpleNamespace(
            tool_calls=[
                {"name": "read_file", "args": {"file_path": "/raw/a.md"}, "id": "1"}
            ]
        ),
        SimpleNamespace(
            type="tool",
            name="read_file",
            tool_call_id="1",
            content="Error: permission denied",
            status="error",
        ),
    ]
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: _fake_agent(result),
    )

    with pytest.raises(ValueError, match="inspected"):
        review_knowledge_gaps(settings)


def test_setup_failure_happens_before_agent_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"openai_api_base": None, "llm_model": "local", "openai_api_key": "not-needed"}
    )
    _write_pair(settings, "a.md")
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: pytest.fail("agent should not be created"),
    )

    with pytest.raises(ValueError, match="tool-calling chat endpoint"):
        review_knowledge_gaps(settings)


def test_agent_failure_is_wrapped_with_feature_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _write_pair(settings, "a.md")

    class Agent:
        def invoke(self, payload: object) -> object:
            raise TimeoutError("model timed out")

    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: Agent(),
    )

    with pytest.raises(RuntimeError, match="DeepAgent knowledge-gap review failed"):
        review_knowledge_gaps(settings)


def test_selected_files_outside_project_root_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    project.mkdir()
    raw.mkdir()
    wiki.mkdir()
    settings = Settings(
        project_root=project,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        openai_api_base="http://localhost/v1",
        llm_model="test",
    )
    _write_pair(settings, "a.md")
    monkeypatch.setattr(
        "wiki_langgraph.knowledge_gap_review.create_wiki_deep_agent",
        lambda **_: pytest.fail("agent should not be created"),
    )

    with pytest.raises(ValueError, match="outside project root"):
        review_knowledge_gaps(settings)
