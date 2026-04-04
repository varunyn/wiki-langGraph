"""Unit tests for llm_author helpers (provenance frontmatter, no LLM calls needed)."""

from wiki_langgraph.llm_author import _inject_provenance_frontmatter


def test_provenance_prepended_when_no_frontmatter() -> None:
    """compiled_from is added as a new frontmatter block when none exists."""
    out = _inject_provenance_frontmatter("# Note\n\nBody.\n", "raw/note.md")
    assert "compiled_from: raw/note.md" in out
    assert out.startswith("---\n")
    assert "# Note" in out


def test_provenance_merged_into_existing_frontmatter() -> None:
    """compiled_from is inserted inside an existing frontmatter block."""
    md = "---\ntitle: My Note\ntags: [a]\n---\n\n# My Note\n"
    out = _inject_provenance_frontmatter(md, "raw/my-note.md")
    assert out.count("---") >= 2
    assert "compiled_from: raw/my-note.md" in out
    assert "title: My Note" in out
    assert "# My Note" in out


def test_provenance_updates_existing_compiled_from() -> None:
    """If compiled_from already exists in frontmatter it is updated, not duplicated."""
    md = "---\ntitle: T\ncompiled_from: raw/old.md\n---\n\nBody.\n"
    out = _inject_provenance_frontmatter(md, "raw/new.md")
    assert out.count("compiled_from:") == 1
    assert "raw/new.md" in out
    assert "raw/old.md" not in out


def test_provenance_body_preserved() -> None:
    """Document body is intact after frontmatter injection."""
    body = "# Hello\n\nSome [[link]] text.\n"
    out = _inject_provenance_frontmatter(body, "notes/hello.md")
    assert "Some [[link]] text." in out
