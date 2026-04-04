"""Rule-based vault health checks (broken wikilinks, Index drift)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path, PurePosixPath
from typing import Literal

from wiki_langgraph.linking import (
    dedupe_raw_uris_for_wiki,
    extract_wikilink_targets,
    resolve_wikilink_target,
    strip_redundant_wiki_prefix,
    wikilink_display_name,
    _build_stem_index,
    _collect_md_relpaths,
    _frontmatter_title,
)


@dataclass
class LintIssue:
    """One lint finding."""

    code: str
    message: str
    path: str | None = None
    detail: str | None = None


@dataclass
class LintReport:
    """Aggregated lint results."""

    issues: list[LintIssue] = field(default_factory=list)

    def add(self, code: str, message: str, path: str | None = None, detail: str | None = None) -> None:
        self.issues.append(LintIssue(code=code, message=message, path=path, detail=detail))

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.code.startswith("E"))

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.issues if i.code.startswith("W"))


def _index_wikilink_targets(index_body: str) -> set[str]:
    """All ``[[link]]`` display targets in Index (same extraction as notes, minus embeds)."""
    return extract_wikilink_targets(index_body)


# Full wikilink (excludes embeds ``![[...]]``): ``[[target]]``, ``[[target|alias]]``, ``[[target#heading]]``.
_WIKILINK_FULL = re.compile(
    r"(?<!\!)\[\[([^\]#|]+)(\|[^\]]*)?((?:#[^\]]*)?)\]\]",
)


def _wikilink_plain_text(target: str, pipe: str | None, hash_part: str | None) -> str:
    """Turn an unresolved wikilink into readable plain text (lose link syntax)."""
    if pipe and pipe.startswith("|"):
        return pipe[1:].strip()
    t = target.strip()
    if hash_part and hash_part.startswith("#"):
        frag = hash_part[1:].strip()
        return f"{t} · {frag}" if frag else t
    return t


def _build_catalog_labels(all_md: set[str], wiki_root: Path) -> dict[str, str]:
    """Map lowercase label -> canonical ``wikilink_display_name`` for each catalog note."""
    canon: dict[str, str] = {}
    for rel in all_md:
        label = wikilink_display_name(strip_redundant_wiki_prefix(wiki_root, rel))
        canon.setdefault(label.lower(), label)
    return canon


def suggest_wikilink_replacement(
    target: str,
    stem_to_paths: dict[str, list[str]],
    title_to_paths: dict[str, list[str]],
    all_md: set[str],
    wiki_root: Path,
    *,
    cutoff: float = 0.84,
) -> str | None:
    """If ``target`` does not resolve, return one catalog link label to use, else ``None``.

    Uses case-insensitive exact label match, path-suffix heuristics, then
    :func:`difflib.get_close_matches` on canonical labels (single unambiguous hit only).
    """
    if resolve_wikilink_target(target, stem_to_paths, title_to_paths, all_md):
        return None
    t = target.strip()
    if not t:
        return None

    labels_canon = _build_catalog_labels(all_md, wiki_root)
    if t.lower() in labels_canon:
        return labels_canon[t.lower()]

    # Path-style: try matching last segment to a stem
    if "/" in t.removesuffix(".md"):
        last = PurePosixPath(t.removesuffix(".md")).name
        key = PurePosixPath(last).stem.lower()
        paths = stem_to_paths.get(key, [])
        if len(paths) == 1:
            return wikilink_display_name(strip_redundant_wiki_prefix(wiki_root, paths[0]))

    pool = sorted(set(labels_canon.values()))
    matches = get_close_matches(t, pool, n=3, cutoff=cutoff)
    if len(matches) == 1:
        return matches[0]

    # Shorter query: last path component vs stems as display names
    if "/" in t:
        short = PurePosixPath(t.removesuffix(".md")).name
        stem_pool = [wikilink_display_name(strip_redundant_wiki_prefix(wiki_root, r)) for r in sorted(all_md)]
        m2 = get_close_matches(short, stem_pool, n=3, cutoff=cutoff)
        if len(m2) == 1:
            return m2[0]

    return None


def fix_unresolved_wikilinks(
    raw_root: Path,
    wiki_root: Path,
    rel_uris: list[str],
    *,
    mode: Literal["auto", "strip", "rewrite"] = "auto",
    fuzzy_cutoff: float = 0.84,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """Rewrite **raw** markdown so unresolved ``[[wikilinks]]`` are fixed or stripped.

    - ``rewrite`` / ``auto``: replace with a single suggested catalog label when confident.
    - ``strip`` / ``auto``: turn remaining broken links into plain text (preserves ``|alias``).
    - Edits only files under ``raw_root``; re-run compile to refresh the wiki.

    Returns:
        ``(files_changed, total_replacements, log_lines)``.
    """
    rel_uris = dedupe_raw_uris_for_wiki(wiki_root, list(rel_uris))
    md_relpaths = _collect_md_relpaths(raw_root, rel_uris)
    stem_to_paths = _build_stem_index(md_relpaths)
    all_md = set(md_relpaths)

    title_to_paths: dict[str, list[str]] = {}
    contents: dict[str, str] = {}
    for rel in md_relpaths:
        try:
            text = (raw_root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        contents[rel] = text
        ft = _frontmatter_title(text)
        if ft:
            title_to_paths.setdefault(ft.lower(), []).append(rel)

    do_fuzzy = mode in ("auto", "rewrite")
    do_strip = mode in ("auto", "strip")

    files_changed = 0
    total = 0
    log_lines: list[str] = []

    def _sub_one(text: str) -> tuple[str, int]:
        n_local = 0

        def repl(m: re.Match[str]) -> str:
            nonlocal n_local
            target = m.group(1).strip()
            pipe = m.group(2)
            hash_part = m.group(3)
            if resolve_wikilink_target(target, stem_to_paths, title_to_paths, all_md):
                return m.group(0)
            new_target: str | None = None
            if do_fuzzy:
                new_target = suggest_wikilink_replacement(
                    target,
                    stem_to_paths,
                    title_to_paths,
                    all_md,
                    wiki_root,
                    cutoff=fuzzy_cutoff,
                )
            if new_target is not None:
                n_local += 1
                return f"[[{new_target}{pipe or ''}{hash_part or ''}]]"
            if do_strip:
                n_local += 1
                return _wikilink_plain_text(target, pipe, hash_part)
            return m.group(0)

        out = _WIKILINK_FULL.sub(repl, text)
        return out, n_local

    for rel in md_relpaths:
        text = contents.get(rel)
        if text is None:
            continue
        new_text, n_sub = _sub_one(text)
        if n_sub == 0 or new_text == text:
            continue
        total += n_sub
        msg = f"fix: {rel} ({n_sub} replacement(s))"
        log_lines.append(msg)
        if dry_run:
            files_changed += 1
            continue
        path = raw_root / rel
        path.write_text(new_text, encoding="utf-8")
        files_changed += 1

    return files_changed, total, log_lines


def run_lint(
    raw_root: Path,
    wiki_root: Path,
    rel_uris: list[str],
) -> LintReport:
    """Scan markdown under ``raw_root`` for broken wikilinks and Index drift vs catalog.

    Uses the same dedupe rules as compile (one catalog path per wiki output file).
    Expected Index entries use the same labels as :func:`format_index_markdown` (strip prefix).
    """
    report = LintReport()
    rel_uris = dedupe_raw_uris_for_wiki(wiki_root, list(rel_uris))
    md_relpaths = _collect_md_relpaths(raw_root, rel_uris)
    stem_to_paths = _build_stem_index(md_relpaths)
    all_md = set(md_relpaths)

    contents: dict[str, str] = {}
    title_to_paths: dict[str, list[str]] = {}
    for rel in md_relpaths:
        try:
            text = (raw_root / rel).read_text(encoding="utf-8")
        except OSError as exc:
            report.add("E_READ", f"cannot read {rel}", rel, str(exc))
            continue
        contents[rel] = text
        t = _frontmatter_title(text)
        if t:
            title_to_paths.setdefault(t.lower(), []).append(rel)

    for rel in md_relpaths:
        text = contents.get(rel)
        if text is None:
            continue
        for target in extract_wikilink_targets(text):
            resolved = resolve_wikilink_target(target, stem_to_paths, title_to_paths, all_md)
            if not resolved:
                report.add(
                    "W_UNRESOLVED_WIKILINK",
                    f"wikilink target not in catalog: {target!r}",
                    rel,
                    f"from [[{target}]]",
                )

    for rel in md_relpaths:
        raw_path = raw_root / rel
        if not raw_path.is_file():
            continue
        out_rel = strip_redundant_wiki_prefix(wiki_root, rel)
        wiki_path = wiki_root / out_rel
        if wiki_path.is_file():
            try:
                raw_mtime = raw_path.stat().st_mtime
                wiki_mtime = wiki_path.stat().st_mtime
                if raw_mtime > wiki_mtime:
                    report.add(
                        "W_STALE_WIKI",
                        f"raw source is newer than compiled wiki note (re-run compile): {rel}",
                        out_rel,
                        f"raw mtime {raw_mtime:.0f} > wiki mtime {wiki_mtime:.0f}",
                    )
            except OSError:
                pass

    expected_index_labels: set[str] = set()
    for rel in md_relpaths:
        if PurePosixPath(rel).name.lower() == "index.md":
            continue
        expected_index_labels.add(wikilink_display_name(strip_redundant_wiki_prefix(wiki_root, rel)))

    index_path = wiki_root / "Index.md"
    if index_path.is_file():
        try:
            idx_text = index_path.read_text(encoding="utf-8")
        except OSError:
            idx_text = ""
        idx_targets = _index_wikilink_targets(idx_text)
        missing_in_index = expected_index_labels - idx_targets
        extra_in_index = idx_targets - expected_index_labels
        idx_label = "Index.md"
        for m in sorted(missing_in_index):
            report.add(
                "W_INDEX_DRIFT",
                f"compiled note not listed in Index: [[{m}]]",
                idx_label,
                None,
            )
        for x in sorted(extra_in_index):
            report.add(
                "W_INDEX_DRIFT",
                f"Index lists [[{x}]] with no matching compiled note label",
                idx_label,
                None,
            )

    return report
