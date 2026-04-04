"""Tests for Obsidian frontmatter merge (flat wiki_langgraph_* provenance only)."""

from wiki_langgraph.frontmatter_graph import (
    WG_COMPILED,
    WG_VERSION,
    WikiGraphFrontmatterStats,
    merge_wiki_graph_frontmatter,
)


def test_merge_prepends_frontmatter_when_missing() -> None:
    stats = WikiGraphFrontmatterStats(compiled_at_iso="2026-01-01T00:00:00Z")
    out = merge_wiki_graph_frontmatter("# Hi\n", stats=stats)
    assert out.startswith("---\n")
    assert "tags:" not in out
    assert f"{WG_VERSION}:" in out
    assert f"{WG_COMPILED}:" in out
    assert "outgoing_links" not in out
    assert "wiki_langgraph:\n" not in out
    assert "# Hi" in out


def test_merge_preserves_user_tags_strips_pipeline_tags() -> None:
    stats = WikiGraphFrontmatterStats(compiled_at_iso="2026-01-01T00:00:00Z")
    src = """---
title: My Doc
aliases:
  - MD
tags:
  - project
  - wiki-langgraph/compiled
---

# Body
"""
    out = merge_wiki_graph_frontmatter(src, stats=stats)
    assert "title: My Doc" in out
    assert "project" in out
    assert "wiki-langgraph/" not in out
    assert "wiki_langgraph_see_also" not in out


def test_merge_replaces_nested_legacy_wiki_langgraph() -> None:
    stats = WikiGraphFrontmatterStats(compiled_at_iso="2026-02-01T12:00:00Z")
    src = """---
title: X
wiki_langgraph:
  version: 1
  compiled_at: '2020-01-01T00:00:00Z'
  outgoing_links: 9
---

# Body
"""
    out = merge_wiki_graph_frontmatter(src, stats=stats)
    assert "wiki_langgraph:\n" not in out
    assert "outgoing_links" not in out
    assert "2026-02-01T12:00:00Z" in out


def test_merge_strips_legacy_flat_counters() -> None:
    stats = WikiGraphFrontmatterStats(compiled_at_iso="2026-03-01T00:00:00Z")
    src = """---
wiki_langgraph_outgoing_links: 99
wiki_langgraph_see_also: 1
wiki_langgraph_backlinks_in: 2
---

# Body
"""
    out = merge_wiki_graph_frontmatter(src, stats=stats)
    assert "99" not in out
    assert "wiki_langgraph_outgoing" not in out


def test_merge_invalid_yaml_unchanged() -> None:
    stats = WikiGraphFrontmatterStats(compiled_at_iso="2026-01-01T00:00:00Z")
    bad = "---\n[ broken\n---\n\n# x\n"
    assert merge_wiki_graph_frontmatter(bad, stats=stats) == bad
