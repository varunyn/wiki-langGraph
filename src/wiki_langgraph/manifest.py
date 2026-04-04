"""Incremental compile: track raw file content hashes between runs."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_VERSION = 1


def default_manifest_path(project_root: Path) -> Path:
    """Default path: ``data/.wiki-langgraph/manifest.json`` under project root."""
    return project_root / "data" / ".wiki-langgraph" / "manifest.json"


def file_sha256(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def str_sha256(text: str) -> str:
    """SHA-256 hex digest of a UTF-8 string (for in-memory content hashing)."""
    return hashlib.sha256(text.encode()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    """Load manifest JSON; return empty structure if missing or invalid.

    Preserves all known sections: ``hashes`` (raw content hashes for incremental
    llm_compile) and ``semantic_edges`` (cached related-note graph for incremental
    semantic link computation).
    """
    if not path.is_file():
        return {"version": MANIFEST_VERSION, "hashes": {}, "semantic_edges": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": MANIFEST_VERSION, "hashes": {}, "semantic_edges": {}}

        raw_hashes = data.get("hashes") or {}
        hashes: dict[str, str] = {
            k: v for k, v in raw_hashes.items() if isinstance(k, str) and isinstance(v, str)
        }

        raw_sem = data.get("semantic_edges") or {}
        sem: dict[str, dict[str, object]] = {}
        for k, v in raw_sem.items():
            if isinstance(k, str) and isinstance(v, dict):
                sem[k] = v

        return {
            "version": int(data.get("version", MANIFEST_VERSION)),
            "hashes": hashes,
            "semantic_edges": sem,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("manifest load failed %s: %s", path, exc)
        return {"version": MANIFEST_VERSION, "hashes": {}, "semantic_edges": {}}


def save_manifest(
    path: Path,
    hashes: dict[str, str],
    *,
    semantic_edges: dict[str, dict[str, object]] | None = None,
) -> None:
    """Write manifest atomically (best-effort).

    Args:
        path: Destination path.
        hashes: Raw content SHA-256 hashes per relpath.
        semantic_edges: Optional cached semantic edge graph
            ``{rel: {"hash": str, "edges": list[str]}}``.
            When omitted the existing section on disk is not updated.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "hashes": dict(sorted(hashes.items())),
    }
    if semantic_edges is not None:
        payload["semantic_edges"] = {k: semantic_edges[k] for k in sorted(semantic_edges)}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def changed_md_relpaths(
    raw_root: Path,
    md_relpaths: list[str],
    manifest: dict[str, Any],
    *,
    incremental: bool,
) -> list[str]:
    """Return markdown rel paths that need LLM re-authoring (raw changed or unknown).

    When ``incremental`` is False, returns all ``md_relpaths``.
    """
    if not incremental:
        return list(md_relpaths)
    stored: dict[str, str] = manifest.get("hashes") or {}
    changed: list[str] = []
    for rel in md_relpaths:
        p = raw_root / rel
        if not p.is_file():
            continue
        try:
            digest = file_sha256(p)
        except OSError:
            changed.append(rel)
            continue
        if stored.get(rel) != digest:
            changed.append(rel)
    return sorted(changed)


def update_hashes_for_relpaths(raw_root: Path, rels: list[str], manifest: dict[str, Any]) -> dict[str, str]:
    """Merge current raw hashes for ``rels`` into manifest's hash map."""
    hashes: dict[str, str] = dict(manifest.get("hashes") or {})
    for rel in rels:
        p = raw_root / rel
        if p.is_file():
            try:
                hashes[rel] = file_sha256(p)
            except OSError as exc:
                logger.debug("manifest skip %s: %s", rel, exc)
    return hashes
