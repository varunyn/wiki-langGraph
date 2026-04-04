"""Semantic related notes via QMD local search (scores, no per-file LLM)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import PurePosixPath
from typing import Any

from wiki_langgraph.config import Settings
from wiki_langgraph.linking import wikilink_display_name

logger = logging.getLogger(__name__)

QUERY_MAX_CHARS = 500


def _qmd_subprocess_env(settings: Settings) -> dict[str, str]:
    """Environment for ``qmd`` CLI: optional CPU-only node-llama-cpp (no Metal on macOS)."""
    env = dict(os.environ)
    if settings.qmd_cpu_only:
        env["NODE_LLAMA_CPP_GPU"] = "false"
    return env


def _slug_segment(segment: str) -> str:
    """Match QMD slug rules (see obsidian-cli skill): lower, spaces and dots → dashes."""
    s = segment.lower()
    return s.replace(" ", "-").replace(".", "-")


def vault_relpath_to_qmd_slug(rel: str) -> str:
    """Vault-relative path as QMD-style slash path (slugified segments, ``.md`` kept)."""
    out: list[str] = []
    for part in PurePosixPath(rel).parts:
        lower = part.lower()
        if lower.endswith(".md"):
            psub = PurePosixPath(part)
            stem_slug = _slug_segment(psub.stem)
            out.append(f"{stem_slug}{psub.suffix.lower()}")
        else:
            out.append(_slug_segment(part))
    return str(PurePosixPath(*out)).replace("\\", "/")


def qmd_uri_to_slash_path(uri: str, collection: str) -> str | None:
    """Return slugified slash path from ``qmd://collection/...`` URI."""
    prefix = f"qmd://{collection}/"
    if not uri.startswith(prefix):
        return None
    return uri[len(prefix) :].strip().lower()


def find_relpath_for_qmd_file(
    file_field: str,
    catalog: list[str],
    collection: str,
) -> str | None:
    """Map a QMD result ``file`` field to a catalog posix relpath."""
    if file_field.startswith("qmd://"):
        slash = qmd_uri_to_slash_path(file_field, collection)
        if slash:
            want = slash.lower()
            for rel in catalog:
                if vault_relpath_to_qmd_slug(rel).lower() == want:
                    return rel
        return None
    # Some builds may emit filesystem paths
    raw = file_field.strip()
    for rel in catalog:
        if rel == raw or rel.endswith(raw) or raw.endswith(rel):
            return rel
    return None


def _strip_frontmatter_for_query(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip()


def query_text_from_body(body: str, max_chars: int = QUERY_MAX_CHARS) -> str:
    """Short query string for QMD from note body."""
    t = _strip_frontmatter_for_query(body)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        t = t[: max_chars - 3] + "..."
    return t or "note"


def _extract_json_array(stdout: str) -> list[dict[str, Any]]:
    """Parse first JSON array from QMD stdout (may include progress text)."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(stdout):
        if ch != "[":
            continue
        try:
            obj, _end = dec.raw_decode(stdout[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    return []


def qmd_query_json(
    query: str,
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Run ``qmd query ... --json`` and return result objects (file, score, ...)."""
    qmd_bin = settings.qmd_bin
    exe = qmd_bin.split()[0] if qmd_bin else "qmd"
    if not shutil.which(exe):
        logger.warning("QMD binary not found on PATH (%s); skipping QMD semantic links", exe)
        return []

    cmd = [
        qmd_bin,
        "query",
        query,
        "-c",
        settings.qmd_collection,
        "--json",
        "-n",
        str(settings.qmd_top_n),
        "--min-score",
        str(settings.qmd_min_score),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.qmd_query_timeout_sec,
            check=False,
            env=_qmd_subprocess_env(settings),
        )
    except subprocess.TimeoutExpired:
        logger.warning("qmd query timed out after %ss", settings.qmd_query_timeout_sec)
        return []

    if proc.returncode != 0:
        logger.warning(
            "qmd query failed (exit %s): %s",
            proc.returncode,
            (proc.stderr or proc.stdout or "")[:800],
        )
        return []

    rows = _extract_json_array(proc.stdout)
    logger.debug("qmd raw hits: %s", len(rows))
    return rows


def suggest_related_via_qmd(
    settings: Settings,
    current_relpath: str,
    body: str,
    catalog: list[str],
) -> list[str]:
    """Return related vault relpaths using QMD search scores (catalog-only)."""
    others = [p for p in catalog if p != current_relpath]
    if not others:
        return []

    query = query_text_from_body(body)
    rows = qmd_query_json(query, settings=settings)
    if not rows:
        return []

    scored: list[tuple[float, str]] = []
    for row in rows:
        file_field = row.get("file")
        if not isinstance(file_field, str):
            continue
        score = row.get("score")
        try:
            sc = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            sc = 0.0
        matched = find_relpath_for_qmd_file(
            file_field,
            others,
            settings.qmd_collection,
        )
        if matched and matched != current_relpath:
            scored.append((sc, matched))

    scored.sort(key=lambda x: -x[0])
    out: list[str] = []
    seen: set[str] = set()
    for sc, rel in scored:
        if rel in seen:
            continue
        seen.add(rel)
        out.append(rel)
        logger.debug(
            "qmd match %s -> %s score=%.3f",
            wikilink_display_name(current_relpath),
            rel,
            sc,
        )
        if len(out) >= settings.qmd_top_n:
            break

    logger.info(
        "qmd semantic: %s -> %s related (from %s hits)",
        current_relpath,
        len(out),
        len(rows),
    )
    return out


def run_qmd_refresh(settings: Settings) -> tuple[bool, str]:
    """Run ``qmd update`` then ``qmd embed -c <collection>`` so the index matches the vault."""
    exe = settings.qmd_bin.split()[0] if settings.qmd_bin else "qmd"
    if not shutil.which(exe):
        return False, f"qmd not found: {exe}"

    parts: list[str] = []
    for args in (
        [settings.qmd_bin, "update"],
        [settings.qmd_bin, "embed", "-c", settings.qmd_collection],
    ):
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=settings.qmd_refresh_timeout_sec,
                check=False,
                env=_qmd_subprocess_env(settings),
            )
        except subprocess.TimeoutExpired:
            return False, f"timeout: {' '.join(args)}"
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:500]
            return False, f"{' '.join(args)} exit {proc.returncode}: {err}"
        parts.append(f"ok: {' '.join(args[:3])}")

    return True, "; ".join(parts)
