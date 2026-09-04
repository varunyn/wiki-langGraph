"""Bounded, read-only DeepAgent review of editorial knowledge gaps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wiki_langgraph.config import Settings
from wiki_langgraph.deep_agent import create_wiki_deep_agent
from wiki_langgraph.linking import (
    _build_stem_index,
    _frontmatter_title,
    dedupe_raw_uris_for_wiki,
    extract_wikilink_targets,
    resolve_wikilink_target,
    strip_redundant_wiki_prefix,
)
from wiki_langgraph.lint import _without_code, run_lint

Category = Literal[
    "missing_concept",
    "missing_overview",
    "weak_connection",
    "possible_duplicate",
    "possible_conflict",
    "source_coverage_gap",
]
Priority = Literal["high", "medium", "low"]
_RELEVANT_LINT_CODES = {"W_ORPHAN_NOTE", "W_UNRESOLVED_WIKILINK"}
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class KnowledgeGapEvidence(BaseModel):
    """One observation from a file the DeepAgent successfully inspected."""

    model_config = ConfigDict(extra="forbid")

    path: str
    observation: str = Field(min_length=1)


class KnowledgeGapFinding(BaseModel):
    """One validated editorial recommendation."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    affected_paths: list[str] = Field(min_length=1)
    evidence: list[KnowledgeGapEvidence] = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    uncertainty: str | None = None


class KnowledgeGapAgentResponse(BaseModel):
    """Structured fields controlled by the DeepAgent rather than the orchestrator."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    insufficient_evidence: list[str] = Field(default_factory=list)
    findings: list[KnowledgeGapFinding] = Field(default_factory=list)


@dataclass(frozen=True)
class KnowledgeGapReviewResult:
    """Auditable deterministic coverage plus validated agent findings."""

    scope: str | None
    partial: bool
    reviewed_paths: list[str]
    omitted_count: int
    summary: str
    insufficient_evidence: list[str]
    findings: list[KnowledgeGapFinding]
    read_allowlist: list[str]

    def render_markdown(self) -> str:
        """Render the validated report deterministically."""
        return _render(self)

    @property
    def report(self) -> str:
        """Backward-compatible rendered report for simple CLI consumers."""
        return self.render_markdown()


@dataclass(frozen=True)
class _Record:
    rel: str
    raw: Path | None
    wiki: Path | None
    title: str
    outgoing_authored_links: tuple[str, ...]
    incoming_authored_links: tuple[str, ...]
    outgoing_link_count: int
    lint_codes: tuple[str, ...]
    reason: str


def _normalize_scope(scope: str | None, raw_root: Path, wiki_root: Path) -> str | None:
    if scope is None:
        return None
    if not scope.strip() or "~" in scope:
        raise ValueError("scope must be a non-empty relative POSIX path")
    p = PurePosixPath(scope)
    if p.is_absolute() or ".." in p.parts or "\\" in scope:
        raise ValueError("scope must be a relative POSIX path without traversal")
    for root in (raw_root, wiki_root):
        candidate = (root / Path(*p.parts)).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            raise ValueError("scope escapes configured data root") from None
    return strip_redundant_wiki_prefix(wiki_root, p.as_posix()).rstrip("/")


def _markdown_files(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    out: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            raise ValueError(f"selected path escapes configured data root: {path}") from None
        rel = path.relative_to(root).as_posix()
        if PurePosixPath(rel).name.lower() in {"index.md", "log.md"}:
            continue
        out[rel] = path
    return out


def _scope_exists(
    scope: str | None,
    raw_root: Path,
    wiki_root: Path,
    raw_files: dict[str, Path],
    wiki_files: dict[str, Path],
) -> bool:
    if scope is None:
        return True
    direct_wiki_scope = wiki_root / Path(*PurePosixPath(scope).parts)
    if direct_wiki_scope.is_dir() or (
        direct_wiki_scope.is_file() and direct_wiki_scope.suffix.lower() == ".md"
    ):
        return True
    if any(
        logical == scope or logical.startswith(scope + "/")
        for logical in (
            strip_redundant_wiki_prefix(wiki_root, raw_rel)
            for raw_rel in raw_files
        )
    ):
        return True
    if any(wiki_rel == scope or wiki_rel.startswith(scope + "/") for wiki_rel in wiki_files):
        return True
    for path in raw_root.rglob("*") if raw_root.is_dir() else ():
        if not path.is_dir():
            continue
        try:
            path.resolve().relative_to(raw_root.resolve())
        except ValueError:
            raise ValueError(f"scope escapes configured data root: {path}") from None
        raw_rel = path.relative_to(raw_root).as_posix()
        if strip_redundant_wiki_prefix(wiki_root, raw_rel) == scope:
            return True
    return False


def _records(settings: Settings, scope: str | None, limit: int) -> tuple[list[_Record], int]:
    raw_root, wiki_root = settings.raw_dir(), settings.wiki_dir()
    raw_files = _markdown_files(raw_root)
    wiki_files = _markdown_files(wiki_root)
    if not _scope_exists(scope, raw_root, wiki_root, raw_files, wiki_files):
        raise ValueError(f"scope does not exist in the configured raw or wiki roots: {scope}")

    def in_scope(rel: str) -> bool:
        return scope is None or rel == scope or rel.startswith(scope.rstrip("/") + "/")

    raw: dict[str, Path] = {}
    selected_raw_rels = dedupe_raw_uris_for_wiki(wiki_root, list(raw_files))
    for raw_rel in selected_raw_rels:
        logical = strip_redundant_wiki_prefix(wiki_root, raw_rel)
        if in_scope(logical):
            raw[logical] = raw_files[raw_rel]
    wiki: dict[str, Path] = {}
    for wiki_rel, path in wiki_files.items():
        if in_scope(wiki_rel):
            wiki[wiki_rel] = path
    rels = sorted(set(raw) | set(wiki))
    try:
        lint = run_lint(raw_root, wiki_root, list(raw_files), okf=False)
        by_path: dict[str, list[str]] = {}
        for issue in lint.issues:
            if issue.path and issue.code in _RELEVANT_LINT_CODES:
                logical = strip_redundant_wiki_prefix(wiki_root, issue.path)
                if in_scope(logical):
                    by_path.setdefault(logical, []).append(issue.code)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot analyze selected notes: {exc}") from exc
    all_raw: dict[str, Path] = {
        strip_redundant_wiki_prefix(wiki_root, raw_rel): raw_files[raw_rel]
        for raw_rel in selected_raw_rels
    }
    all_raw_text: dict[str, str] = {}
    title_to_paths: dict[str, list[str]] = {}
    for rel, path in all_raw.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read note metadata {rel}: {exc}") from exc
        all_raw_text[rel] = text
        frontmatter_title = _frontmatter_title(text)
        if frontmatter_title:
            title_to_paths.setdefault(frontmatter_title.lower(), []).append(rel)

    all_md = set(all_raw)
    stem_to_paths = _build_stem_index(sorted(all_md))
    outgoing: dict[str, set[str]] = {rel: set() for rel in all_md}
    incoming: dict[str, set[str]] = {rel: set() for rel in all_md}
    for rel, text in all_raw_text.items():
        for target in extract_wikilink_targets(_without_code(text)):
            for resolved in resolve_wikilink_target(
                target,
                stem_to_paths,
                title_to_paths,
                all_md,
            ):
                if resolved == rel:
                    continue
                outgoing[rel].add(resolved)
                incoming[resolved].add(rel)

    records: list[_Record] = []
    for rel in rels:
        codes = tuple(sorted(by_path.get(rel, [])))
        if codes:
            reason = "relevant lint finding"
        elif rel not in raw or rel not in wiki:
            reason = "missing raw/wiki counterpart"
        else:
            reason = "authored-link count"
        title_source = all_raw_text.get(rel)
        if title_source is None and rel in wiki:
            try:
                title_source = wiki[rel].read_text(encoding="utf-8")
            except OSError as exc:
                raise ValueError(f"cannot read note metadata {rel}: {exc}") from exc
        records.append(
            _Record(
                rel=rel,
                raw=raw.get(rel),
                wiki=wiki.get(rel),
                title=_note_title(title_source or "", rel),
                outgoing_authored_links=tuple(sorted(outgoing.get(rel, set()))),
                incoming_authored_links=tuple(sorted(incoming.get(rel, set()))),
                outgoing_link_count=len(outgoing.get(rel, set())),
                lint_codes=codes,
                reason=reason,
            )
        )
    records.sort(
        key=lambda record: (
            not (record.lint_codes or record.raw is None or record.wiki is None),
            -record.outgoing_link_count,
            record.rel,
        )
    )
    return records[:limit], max(0, len(records) - limit)


def _note_title(text: str, rel: str) -> str:
    frontmatter_title = _frontmatter_title(text)
    if frontmatter_title:
        return frontmatter_title
    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return PurePosixPath(rel).stem


def _project_path_to_virtual_path(settings: Settings, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(settings.project_root.resolve()).as_posix()
        return "/" + rel
    except ValueError:
        raise ValueError(f"selected path is outside project root: {path}") from None


def _trace_paths(result: object) -> set[str]:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    paths: set[str] = set()
    pending: dict[str, str] = {}
    for message in messages:
        calls = message.get("tool_calls", []) if isinstance(message, dict) else getattr(message, "tool_calls", [])
        for call in calls or []:
            if isinstance(call, dict):
                name, args, ident = call.get("name", ""), call.get("args", {}), call.get("id")
            else:
                name, args, ident = getattr(call, "name", ""), getattr(call, "args", {}), getattr(call, "id", None)
            if name in {"read_file", "grep"} and ident and isinstance(args, dict):
                tool_path = args.get("file_path") or args.get("path")
                if tool_path:
                    pending[str(ident)] = str(tool_path)
        name = message.get("name", "") if isinstance(message, dict) else getattr(message, "name", "")
        ident = message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", None)
        content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
        role = message.get("role", "") if isinstance(message, dict) else getattr(message, "type", "")
        status = message.get("status") if isinstance(message, dict) else getattr(message, "status", None)
        is_tool_result = "tool" in str(role).lower() or name in {"read_file", "grep"}
        is_success = status in {None, "success"} and not str(content).lower().startswith(
            ("error", "cannot", "permission")
        )
        if ident in pending and is_tool_result and is_success:
            paths.add(pending[ident])
    return paths


def _render(result: KnowledgeGapReviewResult) -> str:
    lines = [
        "# Knowledge-gap review",
        "",
        f"Scope: `{result.scope or '(entire corpus)'}`",
        (
            f"Coverage: {'partial' if result.partial else 'full'}; "
            f"reviewed {len(result.reviewed_paths)}; omitted {result.omitted_count}"
        ),
        f"Read allowlist: {', '.join(result.read_allowlist) or '(none)'}",
        "",
        f"Summary: {result.summary}",
        "",
    ]
    if result.partial:
        lines.append(
            "The review is partial; narrow the scope before concluding that "
            "unreviewed notes contain no gaps."
        )
        lines.append("")
    if result.insufficient_evidence:
        lines += [
            "## Insufficient evidence",
            "",
            *[f"- {item}" for item in result.insufficient_evidence],
            "",
        ]
    lines.append("## Findings")
    for finding in sorted(
        result.findings,
        key=lambda item: (
            _PRIORITY_ORDER[item.priority],
            -item.confidence,
            item.category,
            tuple(item.affected_paths),
        ),
    ):
        lines += [
            "",
            f"### {finding.category} ({finding.priority}, confidence {finding.confidence:.2f})",
            f"Affected: {', '.join(finding.affected_paths)}",
            "Evidence:",
        ]
        lines += [f"- `{e.path}` — {e.observation}" for e in finding.evidence]
        lines += [
            f"Why it matters: {finding.why_it_matters}",
            f"Recommendation: {finding.recommendation}",
        ]
        if finding.uncertainty:
            lines.append(f"Uncertainty: {finding.uncertainty}")
    return "\n".join(lines).rstrip() + "\n"


def review_knowledge_gaps(
    settings: Settings,
    *,
    scope: str | None = None,
    limit: int = 24,
) -> KnowledgeGapReviewResult:
    """Run an auditable, read-only knowledge-gap review."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    normalized = _normalize_scope(scope, settings.raw_dir(), settings.wiki_dir())
    selected, omitted = _records(settings, normalized, limit)
    if not selected:
        return KnowledgeGapReviewResult(
            scope=normalized,
            partial=False,
            reviewed_paths=[],
            omitted_count=0,
            summary="no reviewable notes",
            insufficient_evidence=[],
            findings=[],
            read_allowlist=[],
        )
    for record in selected:
        for path in (record.raw, record.wiki):
            if path is not None:
                try:
                    path.read_text(encoding="utf-8")
                except OSError as exc:
                    raise ValueError(f"cannot read selected note {record.rel}: {exc}") from exc
    read_paths: list[str] = []
    if (settings.project_root.resolve() / "AGENTS.md").is_file():
        read_paths.append("/AGENTS.md")
    read_paths.append("/skills/**")
    read_paths.extend(
        _project_path_to_virtual_path(settings, path)
        for record in selected
        for path in (record.raw, record.wiki)
        if path is not None
    )
    read_paths = list(dict.fromkeys(read_paths))
    if not settings.openai_api_base and (
        settings.llm_model == "local" or settings.openai_api_key == "not-needed"
    ):
        raise ValueError(
            "no usable tool-calling chat endpoint configured; set WIKI_OPENAI_API_BASE "
            "or configure a non-local model with an API key"
        )
    metadata = [
        {
            "path": record.rel,
            "title": record.title,
            "raw_path": (
                _project_path_to_virtual_path(settings, record.raw) if record.raw else None
            ),
            "wiki_path": (
                _project_path_to_virtual_path(settings, record.wiki) if record.wiki else None
            ),
            "outgoing_authored_links": list(record.outgoing_authored_links),
            "incoming_authored_links": list(record.incoming_authored_links),
            "authored_link_count": record.outgoing_link_count,
            "lint": list(record.lint_codes),
            "selection_reason": record.reason,
        }
        for record in selected
    ]
    prompt = (
        "Review these bounded wiki records. Use read_file or grep on the exact virtual paths "
        "before making findings. Return only the structured schema. Evidence.path must equal an "
        "exact successfully inspected virtual path. Duplicate or conflict findings require two "
        "distinct inspected paths and a non-empty uncertainty. affected_paths must use the logical "
        "path values below. Do not write files. Coverage limits are not editorial gaps: an "
        "unselected or inaccessible linked note is insufficient evidence, not a "
        "source_coverage_gap. Use source_coverage_gap only when a supplied record has raw_path or "
        "wiki_path set to null, because that proves a raw/wiki counterpart is missing.\n\n"
        "Review context:\n"
        + json.dumps(
            {
                "partial": omitted > 0,
                "selected_count": len(selected),
                "omitted_count": omitted,
            },
            indent=2,
        )
        + "\n\nRecords:\n"
        + json.dumps(metadata, indent=2)
    )
    agent = create_wiki_deep_agent(
        settings=settings,
        read_only=True,
        read_paths=read_paths,
        response_format=KnowledgeGapAgentResponse,
        system_prompt=(
            "You are a cautious editorial knowledge-gap reviewer. Inspect evidence through the "
            "available filesystem tools and never modify files."
        ),
    )
    try:
        raw_result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    except Exception as exc:
        raise RuntimeError(f"DeepAgent knowledge-gap review failed: {exc}") from exc
    payload = raw_result.get("structured_response") if isinstance(raw_result, dict) else None
    if payload is None and isinstance(raw_result, dict):
        payload = raw_result.get("response")
    try:
        parsed = (
            payload
            if isinstance(payload, KnowledgeGapAgentResponse)
            else KnowledgeGapAgentResponse.model_validate(payload)
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed structured knowledge-gap response: {exc}") from exc
    allowed = set(read_paths)
    inspected = _trace_paths(raw_result)

    def allowed_path(path: str) -> bool:
        return path in inspected and any(
            path == allowed_path_value
            or (
                allowed_path_value.endswith("/**")
                and path.startswith(allowed_path_value[:-3])
            )
            for allowed_path_value in allowed
        )

    reviewed = {record.rel for record in selected}
    for finding in parsed.findings:
        if any(path not in reviewed for path in finding.affected_paths):
            raise ValueError("finding affected_paths must identify reviewed logical paths")
        if any(not allowed_path(evidence.path) for evidence in finding.evidence):
            raise ValueError(
                "finding evidence must cite an allowlisted path successfully inspected by the agent"
            )
        if finding.category in {"possible_duplicate", "possible_conflict"}:
            if len({evidence.path for evidence in finding.evidence}) < 2:
                raise ValueError("duplicate/conflict findings require evidence from two distinct paths")
            if not finding.uncertainty or not finding.uncertainty.strip():
                raise ValueError("duplicate/conflict findings require non-empty uncertainty")
    return KnowledgeGapReviewResult(
        scope=normalized,
        partial=omitted > 0,
        reviewed_paths=[record.rel for record in selected],
        omitted_count=omitted,
        summary=parsed.summary,
        insufficient_evidence=parsed.insufficient_evidence,
        findings=parsed.findings,
        read_allowlist=read_paths,
    )
