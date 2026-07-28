"""Bounded inspect/plan/act/verify control loop for the wiki pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from wiki_langgraph.config import Settings
from wiki_langgraph.manifest import changed_md_relpaths, load_manifest
from wiki_langgraph.nodes import (
    _raw_file_relpaths,
    dedupe_raw_uris_for_wiki,
    select_llm_compile_relpaths,
)
from wiki_langgraph.review_queue import candidate_root
from wiki_langgraph.state import WikiGraphState


@dataclass(frozen=True)
class AgentInspection:
    """Read-only workspace facts used to choose the next bounded action."""

    raw_files: int
    markdown_concepts: int
    selected_files: int
    pending_llm_calls: int
    review_candidates: int


@dataclass(frozen=True)
class AgentPlan:
    """One safe action selected from an inspection."""

    action: str
    reason: str
    inspection: AgentInspection


def inspect_workspace(
    settings: Settings,
    *,
    only: list[str] | None = None,
    limit: int | None = None,
) -> AgentInspection:
    """Inspect raw, manifest, and review state without writing or calling an API."""
    raw = settings.raw_dir()
    wiki = settings.wiki_dir()
    raw_uris = dedupe_raw_uris_for_wiki(wiki, _raw_file_relpaths(raw, exclude_dir=wiki))
    md_relpaths = sorted(rel for rel in raw_uris if rel.lower().endswith(".md"))
    selected = select_llm_compile_relpaths(md_relpaths, only=only, limit=limit)
    pending_calls = 0
    if settings.llm_compile:
        manifest = load_manifest(settings.resolved_manifest_path())
        changed = changed_md_relpaths(
            raw,
            md_relpaths,
            manifest,
            incremental=settings.llm_compile_incremental,
        )
        pending_calls = len(select_llm_compile_relpaths(changed, only=only, limit=limit))

    review_root = candidate_root(settings.project_root)
    review_candidates = (
        sum(1 for path in review_root.iterdir() if path.is_dir() and (path / "metadata.json").is_file())
        if review_root.is_dir()
        else 0
    )
    return AgentInspection(
        raw_files=len(raw_uris),
        markdown_concepts=len(md_relpaths),
        selected_files=len(selected),
        pending_llm_calls=pending_calls,
        review_candidates=review_candidates,
    )


def make_plan(inspection: AgentInspection) -> AgentPlan:
    """Choose one bounded action from inspected state."""
    if inspection.raw_files == 0:
        return AgentPlan("stop", "no raw files found", inspection)
    if inspection.review_candidates:
        return AgentPlan(
            "compile_and_review",
            f"{inspection.review_candidates} candidate(s) already await review",
            inspection,
        )
    return AgentPlan("compile_and_verify", "compile the raw corpus, then verify with lint", inspection)


def format_plan(plan: AgentPlan, *, dry_run: bool) -> list[str]:
    """Render a concise inspect/plan result for the CLI."""
    inspection = plan.inspection
    mode = "dry-run" if dry_run else "execute"
    return [
        f"agent plan ({mode}):",
        f"  inspect: raw_files={inspection.raw_files} markdown_concepts={inspection.markdown_concepts}",
        f"  inspect: selected_files={inspection.selected_files} pending_llm_calls={inspection.pending_llm_calls}",
        f"  inspect: review_candidates={inspection.review_candidates}",
        f"  action: {plan.action} ({plan.reason})",
    ]


def replan_after_verification(state: WikiGraphState, inspection: AgentInspection) -> AgentPlan:
    """Choose whether a verified iteration has a safe automatic next action."""
    error = state.get("last_error")
    if error:
        return AgentPlan("stop_for_review", "verification failed; human review is required", inspection)
    warnings = int(state.get("lint_warning_count", 0))
    if warnings:
        return AgentPlan(
            "stop_for_review",
            f"verification passed with {warnings} warning(s); no safe automatic fix is selected",
            inspection,
        )
    return AgentPlan("stop", "verification is clean", inspection)


def replan_lines(plan: AgentPlan, *, iteration: int, max_iterations: int) -> list[str]:
    """Render the controller's post-verification replan decision."""
    return [f"replan: iteration={iteration}/{max_iterations} next_action={plan.action} ({plan.reason})"]


def verification_lines(state: WikiGraphState) -> list[str]:
    """Render verification facts from the graph result."""
    error = state.get("last_error")
    return [
        f"verify: {'failed' if error else 'passed'}",
        f"verify: raw_files={len(state.get('raw_uris', []))} index_md_written={state.get('index_md_written')}",
        f"verify: warnings={state.get('lint_warning_count', 0)} errors={state.get('lint_error_count', 0)}",
        *([f"verify: error={error}"] if error else []),
    ]
