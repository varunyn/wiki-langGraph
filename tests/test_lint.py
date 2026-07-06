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
    """When index.md exists but omits a catalog label, report drift."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# N\n\nok\n", encoding="utf-8")
    (wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n# Index\n\n- [[other]]\n",
        encoding="utf-8",
    )
    r = run_lint(raw, wiki, ["note.md"])
    assert any(i.code == "W_INDEX_DRIFT" and "note" in i.message.lower() for i in r.issues)


def test_lint_index_drift_ignores_generated_index_self_link(tmp_path: Path) -> None:
    """Index self-links should not count as unmatched note entries."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# N\n\nok\n", encoding="utf-8")
    (wiki / "index.md").write_text("# Index\n\n- [[note]]\n- [[Index]]\n", encoding="utf-8")

    r = run_lint(raw, wiki, ["note.md"])

    assert not any(i.code == "W_INDEX_DRIFT" and "[[Index]]" in i.message for i in r.issues)


def test_lint_index_accepts_markdown_link_entries(tmp_path: Path) -> None:
    """OKF-style Markdown links in Index satisfy index drift lint."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# N\n\nBody.\n", encoding="utf-8")
    (wiki / "index.md").write_text("# Index\n\n* [note](note.md) - compiled wiki note\n", encoding="utf-8")

    r = run_lint(raw, wiki, ["note.md"])

    assert not any(i.code == "W_INDEX_DRIFT" for i in r.issues)


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


def test_lint_warns_when_note_has_no_outgoing_wikilinks(tmp_path: Path) -> None:
    """Notes without outbound [[wikilinks]] are reported as suspect."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "solo.md").write_text("# Solo\n\nBody only.\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["solo.md"])

    assert any(issue.code == "W_ORPHAN_NOTE" and issue.path == "solo.md" for issue in report.issues)


def test_lint_uses_compiled_wiki_links_for_orphan_warning(tmp_path: Path) -> None:
    """A compiled note with injected links should not fail orphan lint because raw lacks links."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "source.md").write_text("# Source\n\nRaw body only.\n", encoding="utf-8")
    (raw / "target.md").write_text("# Target\n\nRaw body only.\n", encoding="utf-8")
    (wiki / "source.md").write_text("# Source\n\n<!-- wiki-langgraph see-also -->\n[[target]]\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["source.md", "target.md"])

    assert not any(issue.code == "W_ORPHAN_NOTE" and issue.path == "source.md" for issue in report.issues)


def test_lint_uses_compiled_markdown_links_for_orphan_warning(tmp_path: Path) -> None:
    """A compiled OKF markdown link should count as an outgoing note link."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "source.md").write_text("# Source\n\nRaw body only.\n", encoding="utf-8")
    (raw / "target.md").write_text("# Target\n\nRaw body only.\n", encoding="utf-8")
    (wiki / "source.md").write_text("# Source\n\n[Target](target.md)\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["source.md", "target.md"])

    assert not any(issue.code == "W_ORPHAN_NOTE" and issue.path == "source.md" for issue in report.issues)


def test_lint_skips_generated_index_note_for_orphan_warning(tmp_path: Path) -> None:
    """Index notes are exempt from the zero-outgoing-links warning."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "index.md").write_text("# Index\n\nGenerated index.\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["index.md"])

    assert not any(issue.code == "W_ORPHAN_NOTE" for issue in report.issues)


def test_lint_skips_frontmatter_index_note_for_orphan_warning(tmp_path: Path) -> None:
    """Notes explicitly marked as index notes are exempt from orphan warnings."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "summary.md").write_text(
        "---\nwiki_langgraph_kind: index\n---\n\n# Summary\n\nNo outgoing links.\n",
        encoding="utf-8",
    )

    report = run_lint(raw, wiki, ["summary.md"])

    assert not any(issue.code == "W_ORPHAN_NOTE" for issue in report.issues)


def test_lint_okf_requires_type_frontmatter_for_concepts(tmp_path: Path) -> None:
    """OKF lint reports concept documents that lack a required type field."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "typed.md").write_text("---\ntype: Note\n---\n\n# Typed\n\n[[missing]]\n", encoding="utf-8")
    (raw / "missing.md").write_text("# Missing Type\n\n[[typed]]\n", encoding="utf-8")
    (raw / "index.md").write_text("# Index\n\n* [Typed](typed.md) - typed note\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["typed.md", "missing.md", "index.md"], okf=True)

    assert any(issue.code == "W_OKF_MISSING_TYPE" and issue.path == "missing.md" for issue in report.issues)
    assert not any(issue.code == "W_OKF_MISSING_TYPE" and issue.path == "typed.md" for issue in report.issues)
    assert not any(issue.code == "W_OKF_MISSING_TYPE" and issue.path == "index.md" for issue in report.issues)


def test_lint_okf_type_can_come_from_compiled_wiki_note(tmp_path: Path) -> None:
    """OKF lint validates the compiled wiki artifact when it exists."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "loose.md").write_text("# Loose\n\nRaw without frontmatter.\n", encoding="utf-8")
    (wiki / "loose.md").write_text("---\ntype: Note\n---\n\n# Loose\n", encoding="utf-8")

    report = run_lint(raw, wiki, ["loose.md"], okf=True)

    assert not any(issue.code == "W_OKF_MISSING_TYPE" for issue in report.issues)
