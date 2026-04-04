"""Tests for QMD slug matching and (mocked) query integration."""

import os
from unittest.mock import patch

from wiki_langgraph.config import Settings
from wiki_langgraph.linking_qmd import (
    _qmd_subprocess_env,
    find_relpath_for_qmd_file,
    suggest_related_via_qmd,
    vault_relpath_to_qmd_slug,
)


def test_qmd_cpu_only_sets_node_llama_gpu_false() -> None:
    """CPU-only mode passes NODE_LLAMA_CPP_GPU=false for node-llama-cpp (Metal off)."""
    cfg = Settings(qmd_cpu_only=True)
    assert _qmd_subprocess_env(cfg)["NODE_LLAMA_CPP_GPU"] == "false"


def test_qmd_cpu_only_off_preserves_env_gpu() -> None:
    """When CPU-only is off, do not override NODE_LLAMA_CPP_GPU."""
    cfg = Settings(qmd_cpu_only=False)
    assert _qmd_subprocess_env(cfg).get("NODE_LLAMA_CPP_GPU") == os.environ.get(
        "NODE_LLAMA_CPP_GPU"
    )


def test_vault_slug_matches_qmd_uri() -> None:
    """QMD file URIs use slugified paths; we map back to catalog relpaths."""
    rel = "20-29 Writing/wiki/Note.md"
    uri = "qmd://cursor/20-29-writing/wiki/note.md"
    assert vault_relpath_to_qmd_slug(rel) == "20-29-writing/wiki/note.md"
    got = find_relpath_for_qmd_file(uri, [rel], "cursor")
    assert got == rel


def test_suggest_related_via_qmd_filters_catalog() -> None:
    """Mock qmd JSON; only catalog paths should appear."""
    rows = [
        {"file": "qmd://cursor/a.md", "score": 0.9},
        {"file": "qmd://cursor/z-other.md", "score": 0.8},
    ]
    cfg = Settings(
        semantic_links=True,
        semantic_backend="qmd",
        qmd_refresh=False,
        qmd_collection="cursor",
        qmd_top_n=5,
        qmd_min_score=0.1,
    )
    catalog = ["a.md", "b.md", "c.md"]
    with patch("wiki_langgraph.linking_qmd.qmd_query_json", return_value=rows):
        out = suggest_related_via_qmd(cfg, "b.md", "# Hello\n\nBody.", catalog)
    assert "a.md" in out
    assert len([x for x in out if "z-other" in x]) == 0
