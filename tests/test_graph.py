"""Smoke tests for the compiled graph."""

from pathlib import Path

from wiki_langgraph.config import Settings
from wiki_langgraph.graph import build_graph, run_once
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
    out = app.invoke(
        {
            "step_log": [],
            "raw_uris": [],
            "index_md_written": False,
            "last_error": None,
        }
    )
    assert "step_log" in out
    assert len(out["step_log"]) == 4


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
