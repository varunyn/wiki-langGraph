"""Tests for incremental compile manifest hashing."""

from pathlib import Path

from wiki_langgraph.manifest import (
    changed_md_relpaths,
    default_manifest_path,
    file_sha256,
    load_manifest,
    prune_semantic_edges,
    save_manifest,
    update_hashes_for_relpaths,
)


def test_default_manifest_path_under_data(tmp_path: Path) -> None:
    """Default manifest lives under data/.wiki-langgraph/."""
    p = default_manifest_path(tmp_path)
    assert p == tmp_path / "data" / ".wiki-langgraph" / "manifest.json"


def test_changed_all_when_not_incremental(tmp_path: Path) -> None:
    """Non-incremental mode re-processes every markdown path."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text("x", encoding="utf-8")
    (raw / "b.md").write_text("y", encoding="utf-8")
    m = load_manifest(tmp_path / "missing.json")
    got = changed_md_relpaths(raw, ["a.md", "b.md"], m, incremental=False)
    assert got == ["a.md", "b.md"]


def test_changed_empty_when_hashes_match(tmp_path: Path) -> None:
    """Incremental mode skips files whose hash matches the manifest."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text("same", encoding="utf-8")
    digest = file_sha256(raw / "a.md")
    m = {"version": 1, "hashes": {"a.md": digest}}
    got = changed_md_relpaths(raw, ["a.md"], m, incremental=True)
    assert got == []


def test_changed_when_content_differs(tmp_path: Path) -> None:
    """Incremental mode lists files when raw content changed."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text("new", encoding="utf-8")
    m = {"version": 1, "hashes": {"a.md": "0" * 64}}
    got = changed_md_relpaths(raw, ["a.md"], m, incremental=True)
    assert got == ["a.md"]


def test_save_and_update_hashes_round_trip(tmp_path: Path) -> None:
    """save_manifest persists hashes; update merges new digests."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text("body", encoding="utf-8")
    path = tmp_path / "manifest.json"
    m = load_manifest(path)
    merged = update_hashes_for_relpaths(raw, ["a.md"], m)
    save_manifest(path, merged)
    m2 = load_manifest(path)
    assert m2["hashes"]["a.md"] == file_sha256(raw / "a.md")


def test_save_and_load_semantic_edges(tmp_path: Path) -> None:
    """semantic_edges section round-trips through save/load."""
    path = tmp_path / "manifest.json"
    edges: dict[str, dict[str, object]] = {
        "a.md": {"hash": "abc123", "edges": ["b.md", "c.md"]},
    }
    save_manifest(path, {}, semantic_edges=edges)
    m = load_manifest(path)
    assert m["semantic_edges"]["a.md"]["hash"] == "abc123"
    assert m["semantic_edges"]["a.md"]["edges"] == ["b.md", "c.md"]


def test_load_manifest_preserves_semantic_edges(tmp_path: Path) -> None:
    """load_manifest returns empty semantic_edges when section is absent."""
    path = tmp_path / "manifest.json"
    save_manifest(path, {"x.md": "abc"})
    m = load_manifest(path)
    assert m["semantic_edges"] == {}


def test_update_hashes_prunes_deleted_relpaths(tmp_path: Path) -> None:
    """Manifest hashes should drop entries for relpaths no longer present in the run."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "keep.md").write_text("body", encoding="utf-8")
    manifest = {"version": 1, "hashes": {"keep.md": "old", "gone.md": "stale"}}

    updated = update_hashes_for_relpaths(raw, ["keep.md"], manifest)

    assert "keep.md" in updated
    assert "gone.md" not in updated


def test_prune_semantic_edges_drops_missing_notes_and_targets() -> None:
    """Semantic cache should keep only existing notes and surviving targets."""
    manifest = {
        "semantic_edges": {
            "keep.md": {"hash": "abc", "edges": ["other.md", "gone.md"]},
            "gone.md": {"hash": "def", "edges": ["keep.md"]},
        }
    }

    pruned = prune_semantic_edges(manifest, ["keep.md", "other.md"])

    assert pruned == {"keep.md": {"hash": "abc", "edges": ["other.md"]}}
