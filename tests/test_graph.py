"""Smoke tests for the compiled graph."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from wiki_langgraph import graph as graph_module
from wiki_langgraph.config import Settings
from wiki_langgraph.graph import build_graph, run_once
from wiki_langgraph.manifest import file_sha256, load_manifest, save_manifest
from wiki_langgraph.nodes import node_ingest


def _isolated_settings(tmp_path: Path) -> Settings:
    """Project-scoped settings so tests do not use ``.env`` raw/wiki overrides."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir(parents=True, exist_ok=True)
    wiki.mkdir(parents=True, exist_ok=True)
    return Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        qmd_refresh=False,
    )


def test_build_graph_compiles(tmp_path: Path) -> None:
    """The compiled graph should be invokable."""
    cfg = _isolated_settings(tmp_path)
    app = build_graph(settings=cfg)
    out = asyncio.run(
        app.ainvoke(
            {
                "step_log": [],
                "raw_uris": [],
                "index_md_written": False,
                "last_error": None,
            }
        )
    )
    assert "step_log" in out
    assert len(out["step_log"]) == 4


def test_build_graph_sets_node_timeouts_and_error_handlers(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """Graph nodes should carry explicit LangGraph timeout/error policies."""
    added: dict[str, dict[str, object]] = {}

    class FakeStateGraph:
        def __init__(self, _state_schema: object) -> None:
            pass

        def add_node(self, name: str, action: object, **kwargs: object) -> None:
            added[name] = kwargs

        def add_edge(self, _src: object, _dest: object) -> None:
            pass

        def compile(self) -> object:
            return object()

    monkeypatch.setattr(graph_module, "StateGraph", FakeStateGraph)

    cfg = _isolated_settings(tmp_path)
    build_graph(settings=cfg)

    assert added["ingest"]["timeout"] == cfg.graph_ingest_timeout_sec
    assert added["compile_wiki"]["timeout"] == cfg.graph_compile_timeout_sec
    assert added["index"]["timeout"] == cfg.graph_index_timeout_sec
    assert added["lint"]["timeout"] == cfg.graph_lint_timeout_sec
    assert all(call["error_handler"] is not None for call in added.values())


def test_run_once_returns_step_log(tmp_path: Path) -> None:
    """run_once should complete without raising."""
    cfg = _isolated_settings(tmp_path)
    state = run_once(settings=cfg)
    assert isinstance(state.get("step_log"), list)


def test_compile_overwrites_index_each_run(tmp_path: Path) -> None:
    """Index.md and compiled notes should refresh each run (wikilinks + backlinks)."""
    cfg = _isolated_settings(tmp_path)
    index = cfg.wiki_dir() / "Index.md"
    index.write_text("old content\n", encoding="utf-8")
    (cfg.raw_dir() / "note.md").write_text("# N\n\nBody.\n", encoding="utf-8")
    (cfg.raw_dir() / "only.txt").write_text("x", encoding="utf-8")

    state = run_once(settings=cfg)
    text = index.read_text(encoding="utf-8")
    assert "old content" not in text
    assert "[[note]]" in text
    assert state.get("index_md_written") is True
    compiled = (cfg.wiki_dir() / "note.md").read_text(encoding="utf-8")
    assert "Body." in compiled
    assert "<!-- wiki-langgraph backlinks -->" not in compiled


def test_ingest_lists_nested_files(tmp_path: Path) -> None:
    """Ingest should include files in subdirectories, as relative posix paths."""
    raw = tmp_path / "raw"
    (raw / "outer" / "inner").mkdir(parents=True)
    (raw / "a.txt").write_text("a", encoding="utf-8")
    (raw / "outer" / "inner" / "b.txt").write_text("b", encoding="utf-8")

    out = node_ingest({}, settings=Settings(data_raw_dir=raw))
    assert out["raw_uris"] == ["a.txt", "outer/inner/b.txt"]


def test_ingest_skips_git_dir(tmp_path: Path) -> None:
    """Ingest should not list files under a .git directory."""
    raw = tmp_path / "raw"
    (raw / ".git" / "objects").mkdir(parents=True)
    (raw / "ok.txt").write_text("x", encoding="utf-8")
    (raw / ".git" / "objects" / "x").write_bytes(b"blob")

    out = node_ingest({}, settings=Settings(data_raw_dir=raw))
    assert out["raw_uris"] == ["ok.txt"]


def test_ingest_skips_nested_wiki_output_dir(tmp_path: Path) -> None:
    """Generated wiki output under the raw root should not feed back into ingest."""
    raw = tmp_path / "vault"
    wiki = raw / "wiki"
    wiki.mkdir(parents=True)
    (raw / "source.md").write_text("# Source\n", encoding="utf-8")
    (wiki / "Index.md").write_text("# Index\n\n[[source]]\n", encoding="utf-8")
    (wiki / "source.md").write_text("# Generated\n", encoding="utf-8")

    out = node_ingest(
        {},
        settings=Settings(
            project_root=tmp_path,
            data_raw_dir=raw,
            data_wiki_dir=wiki,
        ),
    )

    assert out["raw_uris"] == ["source.md"]


def test_run_fails_when_lint_finds_unresolved_wikilink(tmp_path: Path) -> None:
    """Pipeline should set last_error when raw markdown has an unresolved wikilink."""
    cfg = _isolated_settings(tmp_path)
    (cfg.raw_dir() / "bad.md").write_text("# B\n\nSee [[nonexistent-note]].\n", encoding="utf-8")
    state = run_once(settings=cfg)
    assert state.get("last_error")
    assert "lint" in (state.get("last_error") or "").lower()


def test_run_skips_lint_when_disabled(tmp_path: Path) -> None:
    """WIKI_LINT_ON_RUN=false should not fail on lint issues."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir(parents=True, exist_ok=True)
    wiki.mkdir(parents=True, exist_ok=True)
    (raw / "bad.md").write_text("# B\n\n[[missing]]\n", encoding="utf-8")
    cfg = Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        qmd_refresh=False,
        lint_on_run=False,
    )
    state = run_once(settings=cfg)
    assert state.get("last_error") is None
    assert any("skipped" in line.lower() for line in state.get("step_log", []))


def test_run_once_prunes_manifest_entries_for_deleted_notes(tmp_path: Path) -> None:
    """Compile should prune stale manifest hashes and semantic cache entries."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir(parents=True, exist_ok=True)
    wiki.mkdir(parents=True, exist_ok=True)
    manifest_path = tmp_path / "manifest.json"
    cfg = Settings(
        project_root=tmp_path,
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        qmd_refresh=False,
        semantic_links=True,
        semantic_backend="qmd",
        manifest_path=manifest_path,
    )
    manifest_path.write_text(
        '{\n'
        '  "version": 1,\n'
        '  "hashes": {"keep.md": "old", "gone.md": "stale"},\n'
        '  "semantic_edges": {\n'
        '    "keep.md": {"hash": "abc", "edges": ["gone.md"]},\n'
        '    "gone.md": {"hash": "def", "edges": ["keep.md"]}\n'
        '  }\n'
        '}\n',
        encoding="utf-8",
    )
    (raw / "keep.md").write_text("# Keep\n\n[[keep]]\n", encoding="utf-8")

    run_once(settings=cfg)

    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert '"keep.md"' in manifest_text
    assert '"gone.md"' not in manifest_text


def test_default_settings_disable_qmd_refresh_for_minimal_run(tmp_path: Path) -> None:
    """Minimal settings should not require QMD refresh by default."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir(parents=True, exist_ok=True)
    wiki.mkdir(parents=True, exist_ok=True)

    cfg = Settings(project_root=tmp_path, data_raw_dir=raw, data_wiki_dir=wiki)

    assert cfg.qmd_refresh is False


def test_llm_compile_review_risky_applies_safe_new_note(tmp_path: Path) -> None:
    """Risky review mode should not queue straightforward new generated notes."""
    cfg = _isolated_settings(tmp_path)
    cfg = cfg.model_copy(
        update={
            "llm_compile": True,
            "openai_api_base": "http://127.0.0.1:11434/v1",
            "llm_compile_review": "risky",
            "lint_on_run": False,
        }
    )
    (cfg.raw_dir() / "new.md").write_text("# Raw\n\nBody.\n", encoding="utf-8")

    with patch(
        "wiki_langgraph.nodes.author_raw_to_wiki_markdown",
        return_value="---\ncompiled_from: new.md\n---\n\n# Generated\n\nUseful generated body.",
    ):
        state = run_once(settings=cfg)

    assert state.get("last_error") is None
    assert "# Generated" in (cfg.wiki_dir() / "new.md").read_text(encoding="utf-8")
    assert not any((tmp_path / "data" / ".wiki-langgraph" / "candidates").glob("*"))
    manifest = load_manifest(cfg.resolved_manifest_path())
    assert manifest["hashes"]["new.md"] == file_sha256(cfg.raw_dir() / "new.md")


def test_llm_compile_review_risky_queues_existing_overwrite_without_hash_update(
    tmp_path: Path,
) -> None:
    """Risky existing-note rewrites should queue and preserve the old manifest hash."""
    cfg = _isolated_settings(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    cfg = cfg.model_copy(
        update={
            "llm_compile": True,
            "openai_api_base": "http://127.0.0.1:11434/v1",
            "llm_compile_review": "risky",
            "manifest_path": manifest_path,
            "lint_on_run": False,
        }
    )
    (cfg.raw_dir() / "existing.md").write_text("# Raw changed\n\nNew raw body.\n", encoding="utf-8")
    (cfg.wiki_dir() / "existing.md").write_text("# Existing\n\nKeep this reviewed note.\n", encoding="utf-8")
    save_manifest(manifest_path, {"existing.md": "0" * 64})

    with patch(
        "wiki_langgraph.nodes.author_raw_to_wiki_markdown",
        return_value="---\ncompiled_from: existing.md\n---\n\n# Generated\n\nRisky replacement.",
    ):
        state = run_once(settings=cfg)

    assert state.get("last_error") is None
    wiki_text = (cfg.wiki_dir() / "existing.md").read_text(encoding="utf-8")
    assert "Keep this reviewed note." in wiki_text
    assert "Risky replacement." not in wiki_text
    manifest = load_manifest(manifest_path)
    assert manifest["hashes"]["existing.md"] == "0" * 64
    candidate_dirs = list((tmp_path / "data" / ".wiki-langgraph" / "candidates").glob("*"))
    assert len(candidate_dirs) == 1
    metadata = json.loads((candidate_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_relpath"] == "existing.md"
    assert metadata["risk_reasons"] == ["existing_note_overwrite"]


def test_llm_compile_review_all_queues_new_note_without_writing_wiki(tmp_path: Path) -> None:
    """All-review mode should queue even safe new notes and leave wiki output absent."""
    cfg = _isolated_settings(tmp_path)
    cfg = cfg.model_copy(
        update={
            "llm_compile": True,
            "openai_api_base": "http://127.0.0.1:11434/v1",
            "llm_compile_review": "all",
            "lint_on_run": False,
        }
    )
    (cfg.raw_dir() / "new.md").write_text("# Raw\n\nBody.\n", encoding="utf-8")

    with patch(
        "wiki_langgraph.nodes.author_raw_to_wiki_markdown",
        return_value="---\ncompiled_from: new.md\n---\n\n# Generated\n\nUseful generated body.",
    ):
        state = run_once(settings=cfg)

    assert state.get("last_error") is None
    assert not (cfg.wiki_dir() / "new.md").exists()
    assert "new.md" not in load_manifest(cfg.resolved_manifest_path())["hashes"]
    assert len(list((tmp_path / "data" / ".wiki-langgraph" / "candidates").glob("*"))) == 1


def test_llm_compile_incremental_preserves_existing_authored_wiki_note(tmp_path: Path) -> None:
    """Unchanged LLM-authored notes should not be overwritten by raw source on later runs."""
    cfg = _isolated_settings(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    raw_path = cfg.raw_dir() / "stable.md"
    raw_path.write_text("# Raw\n\nUncompiled raw text.\n", encoding="utf-8")
    (cfg.wiki_dir() / "stable.md").write_text(
        "---\ncompiled_from: stable.md\n---\n\n# Authored\n\nCurated generated text.",
        encoding="utf-8",
    )
    save_manifest(manifest_path, {"stable.md": file_sha256(raw_path)})
    cfg = cfg.model_copy(
        update={
            "llm_compile": True,
            "openai_api_base": "http://127.0.0.1:11434/v1",
            "manifest_path": manifest_path,
            "lint_on_run": False,
        }
    )

    with patch("wiki_langgraph.nodes.author_raw_to_wiki_markdown") as author:
        state = run_once(settings=cfg)

    assert state.get("last_error") is None
    author.assert_not_called()
    wiki_text = (cfg.wiki_dir() / "stable.md").read_text(encoding="utf-8")
    assert "Curated generated text." in wiki_text
    assert "Uncompiled raw text." not in wiki_text
