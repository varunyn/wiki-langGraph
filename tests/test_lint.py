"""Tests for vault lint (wikilinks, Index drift, staleness)."""

import time
from pathlib import Path

from wiki_langgraph.linking import _build_stem_index, _collect_md_relpaths, dedupe_raw_uris_for_wiki
from wiki_langgraph.lint import fix_unresolved_wikilinks, run_lint, suggest_wikilink_replacement


def test_lint_unresolved_wikilink(tmp_path: Path) -> None:
    """Broken [[target]] is reported as a warning."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n\n[[missing-note]]\n", encoding="utf-8")
    r = run_lint(raw, wiki, ["a.md"])
    codes = [i.code for i in r.issues]
    assert "W_UNRESOLVED_WIKILINK" in codes


def test_lint_index_missing_entry(tmp_path: Path) -> None:
    """When Index exists but omits a catalog label, report drift."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# N\n\nok\n", encoding="utf-8")
    (wiki / "Index.md").write_text(
        "---\ntitle: Index\n---\n# Index\n\n- [[other]]\n",
        encoding="utf-8",
    )
    r = run_lint(raw, wiki, ["note.md"])
    assert any(i.code == "W_INDEX_DRIFT" and "note" in i.message.lower() for i in r.issues)


def test_lint_stale_wiki_when_raw_newer(tmp_path: Path) -> None:
    """W_STALE_WIKI fires when raw file is newer than compiled wiki note."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    wiki_note = wiki / "note.md"
    wiki_note.write_text("# Old\n", encoding="utf-8")
    time.sleep(0.05)
    raw_note = raw / "note.md"
    raw_note.write_text("# New\n", encoding="utf-8")
    r = run_lint(raw, wiki, ["note.md"])
    assert any(i.code == "W_STALE_WIKI" for i in r.issues)


def test_lint_no_stale_when_wiki_newer(tmp_path: Path) -> None:
    """No W_STALE_WIKI when wiki file is at least as recent as raw."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# R\n", encoding="utf-8")
    time.sleep(0.05)
    (wiki / "note.md").write_text("# W\n", encoding="utf-8")
    r = run_lint(raw, wiki, ["note.md"])
    assert not any(i.code == "W_STALE_WIKI" for i in r.issues)


def test_lint_no_stale_when_wiki_missing(tmp_path: Path) -> None:
    """No W_STALE_WIKI when wiki note does not exist yet (first compile pending)."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# R\n", encoding="utf-8")
    r = run_lint(raw, wiki, ["note.md"])
    assert not any(i.code == "W_STALE_WIKI" for i in r.issues)


def test_fix_strip_unresolved_to_plain(tmp_path: Path) -> None:
    """strip mode removes broken [[wikilinks]] as plain text; preserves |alias."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n\nSee [[missing]] and [[gone|Alias]]\n", encoding="utf-8")
    n_files, n_rep, _ = fix_unresolved_wikilinks(raw, wiki, ["a.md"], mode="strip")
    assert n_files == 1
    assert n_rep == 2
    text = (raw / "a.md").read_text(encoding="utf-8")
    assert "[[missing]]" not in text
    assert "missing" in text
    assert "Alias" in text
    assert "[[gone" not in text


def test_fix_fuzzy_typo_then_clean_lint(tmp_path: Path) -> None:
    """auto mode rewrites a close typo to the catalog label when unambiguous."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "target.md").write_text("# T\n\nok\n", encoding="utf-8")
    (raw / "from.md").write_text("# F\n\n[[Targett]]\n", encoding="utf-8")
    fix_unresolved_wikilinks(raw, wiki, ["target.md", "from.md"], mode="auto", fuzzy_cutoff=0.75)
    out = (raw / "from.md").read_text(encoding="utf-8")
    assert "[[target]]" in out.lower() or "[[Target]]" in out
    r = run_lint(raw, wiki, ["target.md", "from.md"])
    assert not any(i.code == "W_UNRESOLVED_WIKILINK" for i in r.issues)


def test_fix_rewrite_only_leaves_unmatched(tmp_path: Path) -> None:
    """rewrite mode does not strip; unfixable links stay as wikilinks."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n\n[[zzzz_no_catalog_match_qqqq]]\n", encoding="utf-8")
    _, n_rep, _ = fix_unresolved_wikilinks(raw, wiki, ["a.md"], mode="rewrite", fuzzy_cutoff=0.99)
    assert n_rep == 0
    assert "[[zzzz_no_catalog_match_qqqq]]" in (raw / "a.md").read_text(encoding="utf-8")


def test_fix_dry_run_no_write(tmp_path: Path) -> None:
    """dry_run does not modify files."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    orig = "# A\n\n[[x]]\n"
    (raw / "a.md").write_text(orig, encoding="utf-8")
    fix_unresolved_wikilinks(raw, wiki, ["a.md"], mode="strip", dry_run=True)
    assert (raw / "a.md").read_text(encoding="utf-8") == orig


def test_suggest_replacement_none_when_ambiguous(tmp_path: Path) -> None:
    """No suggestion when two notes share similar names (ambiguous)."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "foo.md").write_text("# Foo\n", encoding="utf-8")
    (raw / "foe.md").write_text("# Foe\n", encoding="utf-8")
    md = ["foo.md", "foe.md"]
    rel_uris = dedupe_raw_uris_for_wiki(wiki, md)
    mpaths = _collect_md_relpaths(raw, rel_uris)
    stems = _build_stem_index(mpaths)
    titles: dict[str, list[str]] = {}
    sug = suggest_wikilink_replacement(
        "fo",
        stems,
        titles,
        set(mpaths),
        wiki,
        cutoff=0.5,
    )
    assert sug is None
