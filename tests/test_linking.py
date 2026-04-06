"""Tests for wikilink extraction and backlink compilation."""

import hashlib

from pathlib import Path
from unittest.mock import patch

from wiki_langgraph.linking import (
    BACKLINKS_BEGIN,
    IndexNoteEntry,
    SEMANTIC_IN_BEGIN,
    SEE_ALSO_BEGIN,
    SEE_ALSO_END,
    compile_linked_markdown,
    dedupe_raw_uris_for_wiki,
    extract_wikilink_targets,
    format_index_markdown,
    resolve_wikilink_target,
    strip_redundant_wiki_prefix,
    build_index_entries,
)


def test_extract_wikilinks_obsidian_syntax() -> None:
    """Parse [[Note]], [[Note|alias]], [[Note#H]], exclude ![[embed]]."""
    text = """
See [[Alpha]] and [[Beta|b]] plus [[Gamma#Heading]].
Embed ![[Delta]] but not an embed [[Epsilon]].
"""
    got = extract_wikilink_targets(text)
    assert got == {"Alpha", "Beta", "Gamma", "Epsilon"}


def test_resolve_path_style_link() -> None:
    """Path-style wikilinks match vault-relative suffix."""
    stem_to_paths = {"note": ["x/note.md"]}
    title_to_paths: dict[str, list[str]] = {}
    all_md = {"x/note.md", "other.md"}
    hits = resolve_wikilink_target("x/note", stem_to_paths, title_to_paths, all_md)
    assert hits == ["x/note.md"]


def test_resolve_title_alias() -> None:
    """Frontmatter title can resolve links that use the title text."""
    stem_to_paths: dict[str, list[str]] = {}
    title_to_paths = {"unique title": ["z/t.md"]}
    all_md = {"z/t.md"}
    hits = resolve_wikilink_target("Unique Title", stem_to_paths, title_to_paths, all_md)
    assert hits == ["z/t.md"]


def test_compile_skips_identical_content_write(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "solo.md").write_text("# Solo\n\nNo links.\n", encoding="utf-8")
    compile_linked_markdown(raw, wiki, ["solo.md"])
    first = (wiki / "solo.md").read_text(encoding="utf-8")
    import time; time.sleep(0.05)
    compile_linked_markdown(raw, wiki, ["solo.md"])
    second = (wiki / "solo.md").read_text(encoding="utf-8")
    assert "created:" in first
    assert "created:" in second
    first_created = next(line for line in first.splitlines() if line.startswith("created:"))
    second_created = next(line for line in second.splitlines() if line.startswith("created:"))
    assert first_created == second_created


def test_compile_semantic_cache_hit_skips_recompute(tmp_path: Path) -> None:
    """semantic_cache with matching hash prevents calling the backend."""
    import hashlib
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    body = "# Note\n\nContent.\n"
    (raw / "n.md").write_text(body, encoding="utf-8")
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    cache: dict = {"n.md": {"hash": body_hash, "edges": ["other.md"]}}
    compile_linked_markdown(raw, wiki, ["n.md"], semantic_cache=cache)
    assert cache["n.md"]["hash"] == body_hash


def test_compile_content_overrides_replace_raw(tmp_path: Path) -> None:
    """content_overrides supplies markdown bodies instead of reading raw files."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nIGNORED\n", encoding="utf-8")

    md_n, other, sem = compile_linked_markdown(
        raw,
        wiki,
        ["a.md"],
        content_overrides={"a.md": "# A\n\nFrom override.\n"},
    )
    assert md_n == 1
    assert other == 0
    assert sem == 0
    out = (wiki / "a.md").read_text(encoding="utf-8")
    assert "From override." in out
    assert "IGNORED" not in out


def test_compile_backlinks_round_trip(tmp_path: Path) -> None:
    """b.md should list a.md when a links to [[b]]."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nSee [[b]] for more.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nOrphan.\n", encoding="utf-8")

    md_n, other, sem = compile_linked_markdown(raw, wiki, ["a.md", "b.md"])
    assert md_n == 2
    assert other == 0
    assert sem == 0

    b_out = (wiki / "b.md").read_text(encoding="utf-8")
    assert "## Backlinks" in b_out
    assert "[[a]]" in b_out

    a_out = (wiki / "a.md").read_text(encoding="utf-8")
    assert "See [[b]]" in a_out
    assert "<!-- wiki-langgraph backlinks -->" not in a_out


def test_no_footer_when_no_links(tmp_path: Path) -> None:
    """Single note with no graph edges should not get an empty backlinks block."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "solo.md").write_text("# Solo\n\nNo links.\n", encoding="utf-8")
    md_n, other, sem = compile_linked_markdown(raw, wiki, ["solo.md"])
    assert md_n == 1
    out = (wiki / "solo.md").read_text(encoding="utf-8")
    assert "<!-- wiki-langgraph backlinks -->" not in out


def test_format_index_wikilinks() -> None:
    """Index lists notes as internal links."""
    text = format_index_markdown(["z/a.md", "b.md"])
    assert "[[z/a]]" in text
    assert "[[b]]" in text


def test_format_index_skips_index_md_and_dedupes_labels(tmp_path: Path) -> None:
    """Do not list Index.md in the index; one line per distinct wikilink label."""
    wiki = tmp_path / "vault" / "wiki"
    wiki.mkdir(parents=True)
    text = format_index_markdown(
        ["Index.md", "note.md", "wiki/n.md", "n.md"],
        wiki_root=wiki,
    )
    assert "[[Index]]" not in text
    assert text.count("[[n]]") == 1
    assert "[[note]]" in text


def test_format_index_rich_entries_include_agent_metadata() -> None:
    text = format_index_markdown(
        ["note.md"],
        entries=[
            IndexNoteEntry(
                relpath="note.md",
                label="note",
                created="2026-01-01T00:00:00Z",
                modified="2026-01-02T00:00:00Z",
                compiled_from="raw/note.md",
                tags=("agent", "demo"),
                explicit_links=2,
                backlinks=1,
                semantic_outgoing=3,
                semantic_incoming=4,
            )
        ],
    )
    assert "### [[note]]" in text
    assert "- path: `note.md`" in text
    assert "- created: `2026-01-01T00:00:00Z`" in text
    assert "- modified: `2026-01-02T00:00:00Z`" in text
    assert "- source: `raw/note.md`" in text
    assert "- tags: `agent`, `demo`" in text
    assert "- explicit_links: 2" in text
    assert "- backlinks: 1" in text
    assert "- semantic_outgoing: 3" in text
    assert "- semantic_incoming: 4" in text


def test_build_index_entries_counts_semantic_blocks(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()

    (raw / "a.md").write_text("# A\n\nBody.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nBody.\n", encoding="utf-8")

    (wiki / "a.md").write_text(
        "# A\n\n"
        "<!-- wiki-langgraph see-also -->\n"
        "**See also:** [[b]]\n"
        "<!-- /wiki-langgraph see-also -->\n",
        encoding="utf-8",
    )
    (wiki / "b.md").write_text(
        "# B\n\n"
        "<!-- wiki-langgraph semantic-incoming -->\n"
        "## Related (semantic)\n\n- [[a]]\n"
        "<!-- /wiki-langgraph semantic-incoming -->\n",
        encoding="utf-8",
    )

    entries = build_index_entries(raw, wiki, ["a.md", "b.md"])
    by_label = {entry.label: entry for entry in entries}
    assert by_label["a"].semantic_outgoing == 1
    assert by_label["a"].semantic_incoming == 0
    assert by_label["b"].semantic_outgoing == 0
    assert by_label["b"].semantic_incoming == 1


def test_compile_see_also_excludes_notes_already_linked_in_body(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nSee [[b]].\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nTopic.\n", encoding="utf-8")
    (raw / "c.md").write_text("# C\n\nTopic.\n", encoding="utf-8")

    semantic_cache: dict[str, dict[str, object]] = {
        "a.md": {
            "hash": hashlib.sha256("# A\n\nSee [[b]].\n".encode()).hexdigest(),
            "edges": ["b.md", "c.md"],
        }
    }

    compile_linked_markdown(
        raw,
        wiki,
        ["a.md", "b.md", "c.md"],
        semantic_cache=semantic_cache,
    )

    text = (wiki / "a.md").read_text(encoding="utf-8")
    assert "**See also:** [[c]]" in text
    assert "**See also:** [[b]]" not in text


def test_compile_initializes_created_and_modified_on_new_note(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "new.md").write_text("# New\n\nBody.\n", encoding="utf-8")

    compile_linked_markdown(raw, wiki, ["new.md"])

    out = (wiki / "new.md").read_text(encoding="utf-8")
    assert "created:" in out
    assert "modified:" in out


def test_dedupe_raw_uris_for_wiki_prefers_shorter_path(tmp_path: Path) -> None:
    """Two raw paths that map to the same wiki output keep one source URI."""
    wiki = tmp_path / "vault" / "wiki"
    wiki.mkdir(parents=True)
    out = dedupe_raw_uris_for_wiki(wiki, ["wiki/x.md", "x.md"])
    assert out == ["x.md"]


def test_strip_redundant_wiki_prefix(tmp_path: Path) -> None:
    """Output path should not repeat the wiki folder name when raw URIs include it."""
    wiki = tmp_path / "20-29 Writing" / "wiki"
    wiki.mkdir(parents=True)
    assert strip_redundant_wiki_prefix(wiki, "wiki/Note.md") == "Note.md"
    assert strip_redundant_wiki_prefix(wiki, "20-29 Writing/wiki/Note.md") == "Note.md"
    assert strip_redundant_wiki_prefix(wiki, "other/Note.md") == "other/Note.md"


def test_compile_avoids_nested_wiki_folder(tmp_path: Path) -> None:
    """When wiki_dir ends with .../wiki, do not write .../wiki/wiki/..."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "vault" / "wiki"
    raw.mkdir()
    (raw / "wiki").mkdir()
    (raw / "wiki" / "a.md").write_text("# A\n\nSee [[b]].\n", encoding="utf-8")
    (raw / "wiki" / "b.md").write_text("# B\n\nx\n", encoding="utf-8")

    md_n, other, sem = compile_linked_markdown(raw, wiki, ["wiki/a.md", "wiki/b.md"])
    assert md_n == 2
    assert other == 0
    assert sem == 0
    assert (wiki / "a.md").is_file()
    assert (wiki / "b.md").is_file()
    assert not (wiki / "wiki").exists()

    b_out = (wiki / "b.md").read_text(encoding="utf-8")
    assert "[[a]]" in b_out
    assert "[[wiki/a]]" not in b_out


def test_semantic_two_pass_injects_see_also_and_backlinks(tmp_path: Path) -> None:
    """Semantic edges appear as See also outbound [[wikilinks]]; inbound semantic
    references show under **Related (semantic)**, not under **Backlinks** (authored links only).
    """
    from wiki_langgraph.config import Settings

    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()

    (raw / "new.md").write_text("# New note\n\nPlaintext about topic X.\n", encoding="utf-8")
    (raw / "existing.md").write_text("# Existing note\n\nCovers topic X in depth.\n", encoding="utf-8")

    cfg = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        semantic_links=True,
        semantic_backend="llm",
        openai_api_base="http://localhost:11434/v1",
    )

    # Semantic backend returns "existing.md" as related to "new.md".
    def fake_suggest(settings, rel, body, catalog):  # noqa: ANN001
        if rel == "new.md":
            return ["existing.md"]
        return []

    with patch("wiki_langgraph.linking_llm.suggest_semantic_related", side_effect=fake_suggest):
        md_n, _, sem = compile_linked_markdown(
            raw, wiki, ["new.md", "existing.md"], settings=cfg
        )

    assert md_n == 2
    assert sem > 0

    new_out = (wiki / "new.md").read_text(encoding="utf-8")
    existing_out = (wiki / "existing.md").read_text(encoding="utf-8")

    # new.md must contain a managed See-also block with a wikilink to existing.
    assert SEE_ALSO_BEGIN in new_out
    assert SEE_ALSO_END in new_out
    assert "[[existing]]" in new_out

    # existing.md lists new under Related (semantic), not Backlinks (no authored link).
    assert "## Related (semantic)" in existing_out
    assert SEMANTIC_IN_BEGIN in existing_out
    assert "[[new]]" in existing_out
    assert "## Backlinks" not in existing_out


def test_mutual_semantic_edges_dedupe_backlinks_footer(tmp_path: Path) -> None:
    """Mutual semantic suggestions: no authored Backlinks block; Related (semantic)
    lists the other note unless deduped against outbound See also.
    """
    from wiki_langgraph.config import Settings

    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()

    (raw / "a.md").write_text("# A\n\nTopic.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nTopic.\n", encoding="utf-8")

    cfg = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        semantic_links=True,
        semantic_backend="llm",
        openai_api_base="http://localhost:11434/v1",
    )

    def fake_mutual(settings, rel, body, catalog):  # noqa: ANN001
        if rel == "a.md":
            return ["b.md"]
        if rel == "b.md":
            return ["a.md"]
        return []

    with patch("wiki_langgraph.linking_llm.suggest_semantic_related", side_effect=fake_mutual):
        compile_linked_markdown(raw, wiki, ["a.md", "b.md"], settings=cfg)

    a_out = (wiki / "a.md").read_text(encoding="utf-8")
    b_out = (wiki / "b.md").read_text(encoding="utf-8")

    assert "[[b]]" in a_out
    assert BACKLINKS_BEGIN not in a_out
    assert SEMANTIC_IN_BEGIN not in a_out  # inbound B deduped: already in this note's See also

    assert "[[a]]" in b_out
    assert BACKLINKS_BEGIN not in b_out
    assert SEMANTIC_IN_BEGIN not in b_out  # symmetric: inbound A deduped vs outbound See also


def test_semantic_cache_used_in_two_pass(tmp_path: Path) -> None:
    """When the manifest cache has a matching hash, the semantic backend is not called."""
    from wiki_langgraph.config import Settings

    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()

    body = "# Note\n\nSome content.\n"
    (raw / "a.md").write_text(body, encoding="utf-8")

    import hashlib

    from wiki_langgraph.linking import _strip_generated_blocks

    clean = _strip_generated_blocks(body)
    body_hash = hashlib.sha256(clean.encode()).hexdigest()

    cache: dict = {"a.md": {"hash": body_hash, "edges": []}}

    cfg = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        semantic_links=True,
        semantic_backend="llm",
        openai_api_base="http://localhost:11434/v1",
    )

    called: list[bool] = []

    def fake_suggest(settings, rel, body_text, catalog):  # noqa: ANN001
        called.append(True)
        return []

    with patch("wiki_langgraph.linking_llm.suggest_semantic_related", side_effect=fake_suggest):
        compile_linked_markdown(raw, wiki, ["a.md"], settings=cfg, semantic_cache=cache)

    assert not called, "Semantic backend should not be called when cache hash matches"


def test_see_also_block_stripped_on_recompile(tmp_path: Path) -> None:
    """A 'See also' block written by a previous compile is replaced, not duplicated."""
    from wiki_langgraph.config import Settings

    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()

    (raw / "a.md").write_text("# A\n\nContent about X.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nContent about X.\n", encoding="utf-8")

    cfg = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        semantic_links=True,
        semantic_backend="llm",
        openai_api_base="http://localhost:11434/v1",
    )

    def fake_suggest(settings, rel, body_text, catalog):  # noqa: ANN001
        return ["b.md"] if rel == "a.md" else []

    with patch("wiki_langgraph.linking_llm.suggest_semantic_related", side_effect=fake_suggest):
        compile_linked_markdown(raw, wiki, ["a.md", "b.md"], settings=cfg)
        compile_linked_markdown(raw, wiki, ["a.md", "b.md"], settings=cfg)

    a_out = (wiki / "a.md").read_text(encoding="utf-8")
    assert a_out.count(SEE_ALSO_BEGIN) == 1, "See-also block must not be duplicated on re-compile"
