"""Tests for wikilink extraction and backlink compilation."""

import hashlib
import time
from pathlib import Path
from unittest.mock import patch

from wiki_langgraph.config import Settings
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
    time.sleep(0.05)
    compile_linked_markdown(raw, wiki, ["solo.md"])
    second = (wiki / "solo.md").read_text(encoding="utf-8")
    assert "created:" in first
    assert "created:" in second
    first_created = next(line for line in first.splitlines() if line.startswith("created:"))
    second_created = next(line for line in second.splitlines() if line.startswith("created:"))
    assert first_created == second_created


def test_compile_preserves_existing_created_frontmatter_across_runs(tmp_path: Path) -> None:
    """Repeat compiles preserve the original created timestamp from the compiled note."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "solo.md").write_text("# Solo\n\nNo links.\n", encoding="utf-8")

    with patch("wiki_langgraph.linking.utc_now_iso", side_effect=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]):
        compile_linked_markdown(raw, wiki, ["solo.md"])
        compile_linked_markdown(raw, wiki, ["solo.md"])

    out = (wiki / "solo.md").read_text(encoding="utf-8")

    assert "created: '2026-01-01T00:00:00Z'" in out
    assert "modified: '2026-01-02T00:00:00Z'" in out


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
    assert "[a](a.md)" in b_out

    a_out = (wiki / "a.md").read_text(encoding="utf-8")
    assert "See [b](b.md)" in a_out
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


def test_compile_default_profile_adds_okf_type_frontmatter(tmp_path: Path) -> None:
    """Default output keeps markdown body and adds the required OKF concept type."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "solo.md").write_text("# Solo\n\nNo links.\n", encoding="utf-8")
    settings = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
    )

    compile_linked_markdown(raw, wiki, ["solo.md"], settings=settings)

    out = (wiki / "solo.md").read_text(encoding="utf-8")
    assert out.startswith("---\ntype: Note\n")
    assert "wiki_langgraph_version: 1" in out
    assert "# Solo" in out


def test_compile_okf_profile_converts_body_wikilinks_to_markdown_links(tmp_path: Path) -> None:
    """Authored wikilinks are accepted as input but compiled as OKF markdown links."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nSee [[b]] and [[b|Bee]].\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nTopic.\n", encoding="utf-8")

    compile_linked_markdown(raw, wiki, ["a.md", "b.md"], settings=Settings(data_raw_dir=raw, data_wiki_dir=wiki))

    out = (wiki / "a.md").read_text(encoding="utf-8")
    assert "See [b](b.md) and [Bee](b.md)." in out
    assert "[[b]]" not in out
    assert "[[b|Bee]]" not in out


def test_compile_okf_profile_uses_source_relative_links_for_nested_notes(tmp_path: Path) -> None:
    """OKF Markdown links resolve from the compiled note's directory."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    (raw / "nested").mkdir(parents=True)
    (raw / "nested" / "note.md").write_text("# Note\n\nSee [[target]].\n", encoding="utf-8")
    (raw / "target.md").write_text("# Target\n", encoding="utf-8")

    compile_linked_markdown(raw, wiki, ["nested/note.md", "target.md"])

    out = (wiki / "nested" / "note.md").read_text(encoding="utf-8")
    assert "[target](../target.md)" in out


def test_compile_preserves_okf_reserved_log_files(tmp_path: Path) -> None:
    """OKF log files are preserved as logs, not rewritten into concepts."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    (raw / "nested").mkdir(parents=True)
    log = "# Directory Update Log\n\n## 2026-07-27\n* **Update**: Added a note.\n"
    (raw / "log.md").write_text(log, encoding="utf-8")
    (raw / "nested" / "log.md").write_text(log, encoding="utf-8")
    (raw / "note.md").write_text(
        "---\ntitle: Note\ndescription: A useful note.\n---\n\n# Note\n",
        encoding="utf-8",
    )

    compile_linked_markdown(raw, wiki, ["log.md", "nested/log.md", "note.md"])

    assert (wiki / "log.md").read_text(encoding="utf-8") == log
    assert (wiki / "nested" / "log.md").read_text(encoding="utf-8") == log
    assert [entry.label for entry in build_index_entries(raw, wiki, ["log.md", "nested/log.md", "note.md"])] == ["note"]


def test_compile_okf_profile_uses_markdown_links_for_generated_graph_sections(tmp_path: Path) -> None:
    """OKF output uses standard markdown links for generated navigation."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nBody.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nSee [[a]].\n", encoding="utf-8")
    settings = Settings(
        data_raw_dir=raw,
        data_wiki_dir=wiki,
        output_profile="okf",
    )
    body_hash = hashlib.sha256("# A\n\nBody.\n".encode()).hexdigest()

    compile_linked_markdown(
        raw,
        wiki,
        ["a.md", "b.md"],
        settings=settings,
        semantic_cache={"a.md": {"hash": body_hash, "edges": ["b.md"]}},
    )

    out = (wiki / "a.md").read_text(encoding="utf-8")
    assert "**See also:** [b](b.md)" in out
    assert "- [b](b.md)" in out
    assert "[[b]]" not in out


def test_format_index_wikilinks() -> None:
    """Legacy Obsidian profile can still list notes as wikilinks."""
    text = format_index_markdown(["z/a.md", "b.md"], output_profile="obsidian")
    assert "[[z/a]]" in text
    assert "[[b]]" in text


def test_format_index_skips_index_md_and_dedupes_labels(tmp_path: Path) -> None:
    """Do not list index.md in the index; one line per distinct wikilink label."""
    wiki = tmp_path / "vault" / "wiki"
    wiki.mkdir(parents=True)
    text = format_index_markdown(
        ["index.md", "note.md", "wiki/n.md", "n.md"],
        wiki_root=wiki,
        output_profile="obsidian",
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
        output_profile="obsidian",
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


def test_format_index_okf_profile_uses_standard_markdown_links() -> None:
    text = format_index_markdown(
        ["notes/a.md"],
        entries=[
            IndexNoteEntry(
                relpath="notes/a.md",
                label="a",
                created="2026-01-01T00:00:00Z",
                modified="2026-01-02T00:00:00Z",
                tags=("agent",),
                explicit_links=1,
                backlinks=0,
                semantic_outgoing=0,
                semantic_incoming=0,
            )
        ],
        output_profile="okf",
    )

    assert text.startswith('---\nokf_version: "0.2"\n---\n')
    assert "* [a](notes/a.md) - compiled wiki note" in text
    assert "[[a]]" not in text
    assert "created: `2026-01-01T00:00:00Z`" in text


def test_format_index_okf_profile_uses_note_description() -> None:
    entry = IndexNoteEntry(relpath="note.md", label="note", description="A useful note.")

    out = format_index_markdown(["note.md"], entries=[entry], output_profile="okf")

    assert "- A useful note." in out


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


def test_build_index_entries_skips_generated_index_note(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "note.md").write_text("# Note\n\nBody.\n", encoding="utf-8")
    (wiki / "note.md").write_text("# Note\n\nBody.\n", encoding="utf-8")
    (wiki / "index.md").write_text("# Index\n\n[[note]]\n", encoding="utf-8")

    entries = build_index_entries(raw, wiki, ["note.md", "wiki/index.md"])

    assert [entry.label for entry in entries] == ["note"]


def test_build_index_entries_counts_authored_links_from_okf_compiled_notes(tmp_path: Path) -> None:
    """OKF Markdown conversion must not erase authored graph counts in the index."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    (raw / "a.md").write_text("# A\n\nSee [[b]].\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nBody.\n", encoding="utf-8")

    settings = Settings(data_raw_dir=raw, data_wiki_dir=wiki)
    compile_linked_markdown(raw, wiki, ["a.md", "b.md"], settings=settings)

    entries = build_index_entries(raw, wiki, ["a.md", "b.md"])
    by_label = {entry.label: entry for entry in entries}

    assert by_label["a"].explicit_links == 1
    assert by_label["b"].backlinks == 1


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
    assert "**See also:** [c](c.md)" in text
    assert "**See also:** [b](b.md)" not in text


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
    assert "[a](a.md)" in b_out
    assert "[wiki/a](wiki/a.md)" not in b_out


def test_semantic_two_pass_injects_see_also_and_backlinks(tmp_path: Path) -> None:
    """Semantic edges appear as See also outbound links; inbound semantic
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

    # new.md must contain a managed See-also block with a markdown link to existing.
    assert SEE_ALSO_BEGIN in new_out
    assert SEE_ALSO_END in new_out
    assert "[existing](existing.md)" in new_out

    # existing.md lists new under Related (semantic), not Backlinks (no authored link).
    assert "## Related (semantic)" in existing_out
    assert SEMANTIC_IN_BEGIN in existing_out
    assert "[new](new.md)" in existing_out
    assert "## Backlinks" not in existing_out


def test_backlinks_ignore_preserved_generated_see_also_blocks(tmp_path: Path) -> None:
    """Existing compiled See also blocks are generated links, not authored backlinks."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (raw / "a.md").write_text("# A\n\nRaw body.\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\nRaw body.\n", encoding="utf-8")

    existing_a = (
        "# A\n\nRaw body.\n"
        "<!-- wiki-langgraph see-also -->\n"
        "**See also:** [[b]]\n"
        "<!-- /wiki-langgraph see-also -->\n"
    )

    compile_linked_markdown(
        raw,
        wiki,
        ["a.md", "b.md"],
        content_overrides={"a.md": existing_a},
    )

    b_out = (wiki / "b.md").read_text(encoding="utf-8")
    assert "## Backlinks" not in b_out
    assert "[[a]]" not in b_out


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

    assert "[b](b.md)" in a_out
    assert BACKLINKS_BEGIN not in a_out
    assert SEMANTIC_IN_BEGIN not in a_out  # inbound B deduped: already in this note's See also

    assert "[a](a.md)" in b_out
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
