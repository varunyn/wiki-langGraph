"""CLI tests for run command output behavior."""

from pathlib import Path

from wiki_langgraph.config import Settings

from wiki_langgraph.cli import main


def test_run_verbose_failure_prints_step_log_once(monkeypatch, capsys) -> None:  # noqa: ANN001
    """A failed verbose run should not print the same step log to stdout and stderr."""

    def fake_run_once(*, settings: object) -> dict[str, object]:
        return {
            "raw_uris": ["note.md"],
            "index_md_written": True,
            "last_error": "lint failed with 1 issue(s)",
            "step_log": ["compile: ok", "lint: failed — 1 issue(s)"],
        }

    monkeypatch.setattr("wiki_langgraph.cli.run_once", fake_run_once)

    assert main(["run", "-v"]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert captured.out == ""
    assert combined.count("compile: ok") == 1
    assert combined.count("lint: failed") == 1


def test_run_plan_reports_selected_llm_work_without_running_graph(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "notes").mkdir()
    (raw / "notes" / "a.md").write_text("# A\n", encoding="utf-8")
    (raw / "notes" / "b.md").write_text("# B\n", encoding="utf-8")
    (raw / "other.md").write_text("# Other\n", encoding="utf-8")
    settings = Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        llm_compile=True,
        openai_api_base="http://127.0.0.1:1/v1",
        semantic_links=False,
    )
    monkeypatch.setattr("wiki_langgraph.cli.load_settings", lambda: settings)
    monkeypatch.setattr(
        "wiki_langgraph.cli.run_once",
        lambda **_: (_ for _ in ()).throw(AssertionError("plan must not run the graph")),
    )

    from wiki_langgraph.cli import main

    assert main(["run", "--plan", "--only", "notes/*.md", "--limit", "1"]) == 0

    output = capsys.readouterr().out
    assert "raw files: 3" in output
    assert "selected authoring files: 1" in output
    assert "LLM author calls: 1" in output


def test_agent_dry_run_inspects_without_running_graph(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n", encoding="utf-8")
    settings = Settings(project_root=tmp_path, data_raw_dir=raw, data_wiki_dir=wiki)
    monkeypatch.setattr("wiki_langgraph.cli.load_settings", lambda: settings)
    monkeypatch.setattr(
        "wiki_langgraph.cli.run_once",
        lambda **_: (_ for _ in ()).throw(AssertionError("dry-run must not run the graph")),
    )

    assert main(["agent", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "agent iteration 1/2" in output
    assert "agent plan (dry-run):" in output
    assert "action: compile_and_verify" in output


def test_agent_executes_once_and_reports_verification(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n", encoding="utf-8")
    settings = Settings(project_root=tmp_path, data_raw_dir=raw, data_wiki_dir=wiki)
    monkeypatch.setattr("wiki_langgraph.cli.load_settings", lambda: settings)
    calls: list[dict[str, object]] = []

    def fake_run_once(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"raw_uris": ["a.md"], "index_md_written": True, "last_error": None}

    monkeypatch.setattr("wiki_langgraph.cli.run_once", fake_run_once)

    assert main(["agent", "--only", "a.md", "--limit", "1"]) == 0

    output = capsys.readouterr().out
    assert len(calls) == 1
    assert calls[0]["llm_only"] == ["a.md"]
    assert calls[0]["llm_limit"] == 1
    assert "verify: passed" in output
    assert "replan: iteration=1/2" in output


def test_agent_replans_to_review_when_warnings_remain(monkeypatch, capsys, tmp_path: Path) -> None:  # noqa: ANN001
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n", encoding="utf-8")
    settings = Settings(project_root=tmp_path, data_raw_dir=raw, data_wiki_dir=wiki)
    monkeypatch.setattr("wiki_langgraph.cli.load_settings", lambda: settings)
    calls: list[dict[str, object]] = []

    def fake_run_once(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "raw_uris": ["a.md"],
            "index_md_written": True,
            "last_error": None,
            "lint_warning_count": 2,
            "lint_error_count": 0,
        }

    monkeypatch.setattr("wiki_langgraph.cli.run_once", fake_run_once)

    assert main(["agent", "--max-iterations", "3"]) == 0

    output = capsys.readouterr().out
    assert len(calls) == 1
    assert "replan: iteration=1/3 next_action=stop_for_review" in output
    assert "no safe automatic fix is selected" in output
