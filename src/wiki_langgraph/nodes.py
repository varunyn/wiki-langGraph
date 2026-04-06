"""Graph nodes: ingest, compile to markdown, optional QMD index refresh, lint."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from wiki_langgraph.config import Settings, load_settings
from wiki_langgraph.linking import (
    compile_linked_markdown,
    dedupe_raw_uris_for_wiki,
    format_index_markdown,
    strip_redundant_wiki_prefix,
)
from wiki_langgraph.lint import run_lint
from wiki_langgraph.llm_author import author_raw_to_wiki_markdown
from wiki_langgraph.manifest import (
    changed_md_relpaths,
    load_manifest,
    prune_semantic_edges,
    save_manifest,
    update_hashes_for_relpaths,
)
from wiki_langgraph.state import WikiGraphState

logger = logging.getLogger("wiki_langgraph.nodes")


def _raw_file_relpaths(raw: Path) -> list[str]:
    """Paths relative to ``raw`` for every regular file under it (recursive).

    Skips ``.gitkeep`` files and anything under a ``.git`` directory.
    """
    if not raw.exists():
        return []
    rels: list[str] = []
    for path in raw.rglob("*"):
        if not path.is_file():
            continue
        if path.name == ".gitkeep":
            continue
        rel = path.relative_to(raw)
        if ".git" in rel.parts:
            continue
        rels.append(rel.as_posix())
    return sorted(rels)


def node_ingest(_state: object, *, settings: Settings | None = None) -> dict[str, object]:
    """List existing raw files or create the raw directory; records relative URIs.

    Walks subdirectories of the raw path. ``raw_uris`` entries are posix paths
    relative to the raw root (e.g. ``notes/chapter1.md``).

    Replace this with real fetchers (HTTP, git, APIs) per source.
    """
    cfg = settings or load_settings()
    raw = cfg.raw_dir()
    raw.mkdir(parents=True, exist_ok=True)
    uris = _raw_file_relpaths(raw)
    msg = f"ingest: raw_dir={raw} ({len(uris)} files)"
    logger.info(msg)
    return {
        "step_log": [msg],
        "raw_uris": uris,
        "last_error": None,
    }


def node_compile_wiki(state: WikiGraphState, *, settings: Settings | None = None) -> dict[str, object]:
    """Compile raw markdown into ``wiki_dir`` with resolved backlinks (Obsidian wikilinks).

    Copies each file from the raw tree, appends a **Backlinks** section derived from
    ``[[wikilinks]]`` in the vault (see https://obsidian.md/help/links). Regenerates
    ``Index.md`` with wikilinks to every markdown note.

    When wiring an LLM, use :func:`wiki_langgraph.obsidian_prompt.wiki_llm_system_instructions`
    so generated notes follow Obsidian frontmatter and OFM (wikilinks, callouts, etc.).
    """
    cfg = settings or load_settings()
    raw = cfg.raw_dir()
    wiki = cfg.wiki_dir()
    wiki.mkdir(parents=True, exist_ok=True)
    raw_uris = dedupe_raw_uris_for_wiki(wiki, list(state.get("raw_uris") or []))
    md_only = sorted(p for p in raw_uris if p.lower().endswith(".md"))
    manifest_path = cfg.resolved_manifest_path()

    needs_manifest = cfg.llm_compile or cfg.semantic_links
    manifest_for_run = load_manifest(manifest_path) if needs_manifest else None
    semantic_cache: dict[str, dict[str, object]] = (
        dict(manifest_for_run.get("semantic_edges") or {}) if manifest_for_run is not None else {}
    )

    content_overrides: dict[str, str] | None = None
    if cfg.llm_compile:
        manifest_for_run = load_manifest(manifest_path)
        changed = changed_md_relpaths(
            raw,
            md_only,
            manifest_for_run,
            incremental=cfg.llm_compile_incremental,
        )
        workers = max(1, min(cfg.llm_compile_max_workers, len(changed)))
        logger.info(
            "llm_compile: authoring %d/%d markdown file(s) (incremental=%s, workers=%s)",
            len(changed),
            len(md_only),
            cfg.llm_compile_incremental,
            workers,
        )
        if workers > 1:
            logger.info(
                "llm_compile: workers>1 sends concurrent HTTP requests; if you see many timeouts, "
                "set WIKI_LLM_COMPILE_MAX_WORKERS=1 (typical for local Ollama/llama-server)."
            )
        overrides: dict[str, str] = {}

        def _author_one(rel: str) -> tuple[str, str]:
            raw_text = (raw / rel).read_text(encoding="utf-8")
            existing: str | None = None
            if cfg.llm_compile_enrich:
                wiki_path = wiki / strip_redundant_wiki_prefix(wiki, rel)
                if wiki_path.is_file():
                    try:
                        existing = wiki_path.read_text(encoding="utf-8")
                    except OSError:
                        existing = None
            return rel, author_raw_to_wiki_markdown(
                raw_text,
                rel,
                settings=cfg,
                existing_wiki_text=existing,
            )

        if workers == 1:
            for rel in changed:
                r, text = _author_one(rel)
                overrides[r] = text
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_author_one, rel) for rel in changed]
                for fut in as_completed(futures):
                    r, text = fut.result()
                    overrides[r] = text
        content_overrides = overrides if overrides else None

    md_n, other_n, sem_edges = compile_linked_markdown(
        raw,
        wiki,
        raw_uris,
        settings=cfg,
        content_overrides=content_overrides,
        semantic_cache=semantic_cache if cfg.semantic_links else None,
    )
    if needs_manifest and manifest_for_run is not None:
        new_hashes = update_hashes_for_relpaths(raw, md_only, manifest_for_run)
        pruned_semantic_edges = prune_semantic_edges(manifest_for_run, md_only)
        if cfg.semantic_links:
            pruned_semantic_edges.update(prune_semantic_edges({"semantic_edges": semantic_cache}, md_only))
        save_manifest(
            manifest_path,
            new_hashes,
            semantic_edges=pruned_semantic_edges if cfg.semantic_links else None,
        )
    md_list = md_only
    (wiki / "Index.md").write_text(format_index_markdown(md_list, wiki_root=wiki), encoding="utf-8")
    compile_msg = (
        f"compile: wiki_dir={wiki} md_notes={md_n} other_files={other_n} "
        f"semantic_edges={sem_edges} index_wikilinks={len(md_list)}"
    )
    logger.info(compile_msg)
    return {
        "step_log": [compile_msg],
        "index_md_written": True,
        "last_error": None,
    }


def node_index(_state: object, *, settings: Settings | None = None) -> dict[str, object]:
    """Refresh QMD index when enabled so search matches newly written wiki files."""
    cfg = settings or load_settings()
    wiki = cfg.wiki_dir()
    parts: list[str] = [f"index: wiki_dir={Path(wiki)}"]
    if cfg.qmd_refresh:
        from wiki_langgraph.linking_qmd import run_qmd_refresh

        ok, detail = run_qmd_refresh(cfg)
        if ok:
            parts.append(f"qmd_refresh ok ({detail})")
            logger.info("qmd refresh: %s", detail)
        else:
            parts.append(f"qmd_refresh failed: {detail}")
            logger.warning("qmd refresh failed: %s", detail)
    else:
        parts.append("qmd_refresh=off")

    idx_msg = " ".join(parts)
    logger.info(idx_msg)
    return {
        "step_log": [idx_msg],
        "last_error": None,
    }


def node_lint(_state: object, *, settings: Settings | None = None) -> dict[str, object]:
    """Run vault lint after compile/index; fail the run if any issues are reported."""
    cfg = settings or load_settings()
    if not cfg.lint_on_run:
        msg = "lint: skipped (WIKI_LINT_ON_RUN=false)"
        logger.info(msg)
        return {"step_log": [msg], "last_error": None}

    raw = cfg.raw_dir()
    wiki = cfg.wiki_dir()
    uris = _raw_file_relpaths(raw)
    report = run_lint(raw, wiki, uris)
    n = len(report.issues)
    if n == 0:
        ok_msg = "lint: ok (0 issues)"
        logger.info(ok_msg)
        return {"step_log": [ok_msg], "last_error": None}

    lines: list[str] = [f"lint: failed — {n} issue(s)"]
    for issue in report.issues:
        loc = f"{issue.path}: " if issue.path else ""
        detail = f" ({issue.detail})" if issue.detail else ""
        lines.append(f"{issue.code} {loc}{issue.message}{detail}")
    err = f"lint failed with {n} issue(s)"
    logger.error(err)
    return {"step_log": lines, "last_error": err}
