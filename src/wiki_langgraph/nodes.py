"""Graph nodes: ingest, compile to markdown, optional QMD index refresh, lint."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from fnmatch import fnmatchcase
from pathlib import Path

from wiki_langgraph.config import Settings, load_settings
from wiki_langgraph.linking import (
    build_index_entries,
    compile_linked_markdown,
    dedupe_raw_uris_for_wiki,
    format_index_markdown,
    strip_redundant_wiki_prefix,
    wikilink_display_name,
)
from wiki_langgraph.lint import run_lint
from wiki_langgraph.llm_author import author_raw_to_wiki_markdown
from wiki_langgraph.manifest import (
    changed_md_relpaths,
    file_sha256,
    load_manifest,
    prune_semantic_edges,
    save_manifest,
    update_hashes_for_relpaths,
)
from wiki_langgraph.review_queue import assess_candidate, candidate_root, write_candidate
from wiki_langgraph.state import WikiGraphState

logger = logging.getLogger("wiki_langgraph.nodes")
INDEX_FILENAME = "index.md"


def select_llm_compile_relpaths(
    relpaths: list[str],
    *,
    only: list[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Select LLM authoring inputs without shrinking the deterministic corpus."""
    selected = sorted(relpaths)
    patterns = [pattern for pattern in (only or []) if pattern]
    if patterns:
        selected = [
            rel
            for rel in selected
            if any(fnmatchcase(rel, pattern) for pattern in patterns)
        ]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _raw_file_relpaths(raw: Path, *, exclude_dir: Path | None = None) -> list[str]:
    """Paths relative to ``raw`` for every regular file under it (recursive).

    Skips ``.gitkeep`` files, anything under a ``.git`` directory, and an optional
    generated output directory when it lives under ``raw``.
    """
    if not raw.exists():
        return []
    exclude_resolved = exclude_dir.resolve() if exclude_dir is not None else None
    rels: list[str] = []
    for path in raw.rglob("*"):
        if not path.is_file():
            continue
        if exclude_resolved is not None:
            try:
                path.resolve().relative_to(exclude_resolved)
                continue
            except ValueError:
                pass
        if path.name == ".gitkeep":
            continue
        rel = path.relative_to(raw)
        if ".git" in rel.parts:
            continue
        rels.append(rel.as_posix())
    return sorted(rels)


def _canonical_index_path(wiki_root: Path) -> Path:
    """Return the OKF index path, migrating legacy ``Index.md`` casing if needed."""
    target = wiki_root / INDEX_FILENAME
    has_lowercase_entry = any(path.name == INDEX_FILENAME for path in wiki_root.iterdir())
    for path in wiki_root.iterdir():
        if path.name.lower() != INDEX_FILENAME or path.name == INDEX_FILENAME:
            continue
        if has_lowercase_entry:
            path.unlink()
            continue
        tmp = wiki_root / f".{path.name}.wiki-langgraph-rename"
        suffix = 0
        while tmp.exists():
            suffix += 1
            tmp = wiki_root / f".{path.name}.wiki-langgraph-rename-{suffix}"
        path.rename(tmp)
        tmp.rename(target)
        has_lowercase_entry = True
    return target


def node_ingest(_state: object, *, settings: Settings | None = None) -> dict[str, object]:
    """List existing raw files or create the raw directory; records relative URIs.

    Walks subdirectories of the raw path. ``raw_uris`` entries are posix paths
    relative to the raw root (e.g. ``notes/chapter1.md``).

    Replace this with real fetchers (HTTP, git, APIs) per source.
    """
    cfg = settings or load_settings()
    raw = cfg.raw_dir()
    wiki = cfg.wiki_dir()
    raw.mkdir(parents=True, exist_ok=True)
    uris = _raw_file_relpaths(raw, exclude_dir=wiki)
    msg = f"ingest: raw_dir={raw} ({len(uris)} files)"
    logger.info(msg)
    return {
        "step_log": [msg],
        "raw_uris": uris,
        "last_error": None,
    }


def node_compile_wiki(state: WikiGraphState, *, settings: Settings | None = None) -> dict[str, object]:
    """Compile raw markdown into ``wiki_dir`` with OKF links and resolved backlinks.

    Copies each file from the raw tree, converts resolved source wikilinks to
    standard Markdown links for the default OKF profile, appends a **Backlinks**
    section derived from authored source links, and regenerates ``index.md``.
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
    queued_review_rels: set[str] = set()
    queued_new_rels: set[str] = set()
    queued_review_count = 0
    hash_relpaths = md_only
    if cfg.llm_compile:
        manifest_for_run = load_manifest(manifest_path)
        changed = changed_md_relpaths(
            raw,
            md_only,
            manifest_for_run,
            incremental=cfg.llm_compile_incremental,
        )
        changed = select_llm_compile_relpaths(
            changed,
            only=list(state.get("llm_only") or []),
            limit=state.get("llm_limit"),
        )
        hash_relpaths = (
            md_only
            if not state.get("llm_only") and state.get("llm_limit") is None
            else changed
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
        known_note_titles = sorted(wikilink_display_name(rel) for rel in md_only)

        def _existing_wiki_text(rel: str) -> tuple[str, str | None]:
            target_rel = strip_redundant_wiki_prefix(wiki, rel)
            wiki_path = wiki / target_rel
            if not wiki_path.is_file():
                return target_rel, None
            try:
                return target_rel, wiki_path.read_text(encoding="utf-8")
            except OSError:
                return target_rel, None

        def _author_one(rel: str) -> tuple[str, str, str, str | None]:
            raw_text = (raw / rel).read_text(encoding="utf-8")
            target_rel, existing = _existing_wiki_text(rel)
            authored = author_raw_to_wiki_markdown(
                raw_text,
                rel,
                settings=cfg,
                existing_wiki_text=existing if cfg.llm_compile_enrich else None,
                known_note_titles=known_note_titles,
            )
            return rel, authored, target_rel, existing

        authored_results: list[tuple[str, str, str, str | None]] = []
        if workers == 1:
            for rel in changed:
                authored_results.append(_author_one(rel))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_author_one, rel) for rel in changed]
                for fut in as_completed(futures):
                    authored_results.append(fut.result())

        review_root = candidate_root(cfg.project_root)
        for rel, text, target_rel, existing in authored_results:
            decision = assess_candidate(
                mode=cfg.llm_compile_review,
                relpath=rel,
                generated=text,
                existing=existing,
            )
            if decision.queue:
                queued_review_rels.add(rel)
                queued_review_count += 1
                if existing is None:
                    queued_new_rels.add(rel)
                write_candidate(
                    review_root,
                    relpath=rel,
                    target_relpath=target_rel,
                    generated=text,
                    raw_sha256=file_sha256(raw / rel),
                    reasons=decision.reasons,
                    existing=existing,
                )
                if existing is not None:
                    overrides[rel] = existing
                continue
            overrides[rel] = text

        if cfg.llm_compile_incremental:
            for rel in md_only:
                if rel in changed or rel in overrides:
                    continue
                _, existing = _existing_wiki_text(rel)
                if existing is not None:
                    overrides[rel] = existing
        content_overrides = overrides if overrides else None

    compile_uris = [uri for uri in raw_uris if uri not in queued_new_rels]
    md_n, other_n, sem_edges = compile_linked_markdown(
        raw,
        wiki,
        compile_uris,
        settings=cfg,
        content_overrides=content_overrides,
        semantic_cache=semantic_cache if cfg.semantic_links else None,
    )
    if needs_manifest and manifest_for_run is not None:
        if queued_review_rels:
            existing_hashes = dict(manifest_for_run.get("hashes") or {})
            new_hashes = {rel: digest for rel, digest in existing_hashes.items() if rel in md_only}
            for rel in hash_relpaths:
                if rel in queued_review_rels:
                    continue
                p = raw / rel
                if p.is_file():
                    try:
                        new_hashes[rel] = file_sha256(p)
                    except OSError as exc:
                        logger.debug("manifest skip %s: %s", rel, exc)
        else:
            new_hashes = update_hashes_for_relpaths(raw, hash_relpaths, manifest_for_run)
        pruned_semantic_edges = prune_semantic_edges(manifest_for_run, md_only)
        if cfg.semantic_links:
            pruned_semantic_edges.update(prune_semantic_edges({"semantic_edges": semantic_cache}, md_only))
        save_manifest(
            manifest_path,
            new_hashes,
            semantic_edges=pruned_semantic_edges if cfg.semantic_links else None,
        )
    md_list = [
        rel
        for rel in md_only
        if rel not in queued_new_rels and Path(rel).name.lower() not in {"index.md", "log.md"}
    ]
    index_entries = build_index_entries(raw, wiki, compile_uris)
    _canonical_index_path(wiki).write_text(
        format_index_markdown(
            md_list,
            wiki_root=wiki,
            entries=index_entries,
            output_profile=cfg.output_profile,
        ),
        encoding="utf-8",
    )
    compile_msg = (
        f"compile: wiki_dir={wiki} md_notes={md_n} other_files={other_n} "
        f"semantic_edges={sem_edges} index_links={len(md_list)}"
    )
    if queued_review_count:
        compile_msg += f" llm_review_queued={queued_review_count}"
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
    """Run vault lint after compile/index; optionally treat warnings as non-blocking."""
    cfg = settings or load_settings()
    if not cfg.lint_on_run:
        msg = "lint: skipped (WIKI_LINT_ON_RUN=false)"
        logger.info(msg)
        return {
            "step_log": [msg],
            "last_error": None,
            "lint_issue_count": 0,
            "lint_warning_count": 0,
            "lint_error_count": 0,
        }

    raw = cfg.raw_dir()
    wiki = cfg.wiki_dir()
    uris = _raw_file_relpaths(raw, exclude_dir=wiki)
    report = run_lint(raw, wiki, uris, okf=cfg.output_profile == "okf")
    n = len(report.issues)
    if n == 0:
        ok_msg = "lint: ok (0 issues)"
        logger.info(ok_msg)
        return {
            "step_log": [ok_msg],
            "last_error": None,
            "lint_issue_count": 0,
            "lint_warning_count": 0,
            "lint_error_count": 0,
        }

    lines: list[str] = [f"lint: failed — {n} issue(s)"]
    for issue in report.issues:
        loc = f"{issue.path}: " if issue.path else ""
        detail = f" ({issue.detail})" if issue.detail else ""
        lines.append(f"{issue.code} {loc}{issue.message}{detail}")
    issue_count = report.error_count + report.warn_count
    strict = not isinstance(_state, dict) or _state.get("lint_strict", True)
    if report.error_count == 0 and not strict:
        lines[0] = f"lint: passed with {report.warn_count} warning(s)"
        logger.warning(lines[0])
        return {
            "step_log": lines,
            "last_error": None,
            "lint_issue_count": issue_count,
            "lint_warning_count": report.warn_count,
            "lint_error_count": report.error_count,
        }
    err = f"lint failed with {n} issue(s)"
    logger.error(err)
    return {
        "step_log": lines,
        "last_error": err,
        "lint_issue_count": issue_count,
        "lint_warning_count": report.warn_count,
        "lint_error_count": report.error_count,
    }
