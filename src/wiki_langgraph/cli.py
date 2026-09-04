"""CLI entrypoint for running the LangGraph pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import NoReturn

from wiki_langgraph.agentic import (
    format_plan,
    inspect_workspace,
    make_plan,
    replan_after_verification,
    replan_lines,
    verification_lines,
)
from wiki_langgraph.config import Settings, load_settings
from wiki_langgraph.deep_review import review_candidates
from wiki_langgraph.evaluation import run_agent_experiment, run_research_experiment
from wiki_langgraph.graph import run_once
from wiki_langgraph.knowledge_gap_review import review_knowledge_gaps
from wiki_langgraph.lint import fix_unresolved_wikilinks, run_lint
from wiki_langgraph.logging_config import configure_logging
from wiki_langgraph.manifest import changed_md_relpaths, load_manifest, save_manifest
from wiki_langgraph.nodes import (
    _raw_file_relpaths,
    dedupe_raw_uris_for_wiki,
    select_llm_compile_relpaths,
)
from wiki_langgraph.query import answer_query, research_query, save_query_answer, save_research_brief
from wiki_langgraph.review_queue import candidate_root


def _candidate_dir(root: Path, candidate_id: str) -> Path:
    return root / candidate_id


def _read_candidate_metadata(path: Path) -> dict[str, object]:
    return json.loads((path / "metadata.json").read_text(encoding="utf-8"))


def _review_list(root: Path) -> int:
    if not root.exists():
        print("review: no pending candidates")
        return 0
    candidates = sorted(p for p in root.iterdir() if p.is_dir() and (p / "metadata.json").is_file())
    if not candidates:
        print("review: no pending candidates")
        return 0
    for path in candidates:
        metadata = _read_candidate_metadata(path)
        reasons = ",".join(str(item) for item in metadata.get("risk_reasons", []))
        print(
            f"{metadata.get('id')} "
            f"{metadata.get('source_relpath')} -> {metadata.get('target_relpath')} "
            f"reasons={reasons}"
        )
    return 0


def _review_show(root: Path, candidate_id: str) -> int:
    path = _candidate_dir(root, candidate_id)
    if not path.is_dir():
        print(f"review: candidate not found: {candidate_id}", file=sys.stderr)
        return 1
    metadata = _read_candidate_metadata(path)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    print("\n--- candidate.md ---")
    print((path / "candidate.md").read_text(encoding="utf-8"), end="")
    return 0


def _review_approve(root: Path, candidate_id: str) -> int:
    settings = load_settings()
    path = _candidate_dir(root, candidate_id)
    if not path.is_dir():
        print(f"review: candidate not found: {candidate_id}", file=sys.stderr)
        return 1
    metadata = _read_candidate_metadata(path)
    target_rel = metadata.get("target_relpath")
    source_rel = metadata.get("source_relpath")
    raw_sha256 = metadata.get("raw_sha256")
    if not isinstance(target_rel, str) or not isinstance(source_rel, str) or not isinstance(raw_sha256, str):
        print(f"review: invalid candidate metadata: {candidate_id}", file=sys.stderr)
        return 1
    target = settings.wiki_dir() / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((path / "candidate.md").read_text(encoding="utf-8"), encoding="utf-8")

    manifest_path = settings.resolved_manifest_path()
    manifest = load_manifest(manifest_path)
    hashes = dict(manifest.get("hashes") or {})
    hashes[source_rel] = raw_sha256
    save_manifest(
        manifest_path,
        hashes,
        semantic_edges=dict(manifest.get("semantic_edges") or {}),
    )
    shutil.rmtree(path)
    print(f"approved {candidate_id}: wrote {target_rel}")
    return 0


def _review_reject(root: Path, candidate_id: str) -> int:
    path = _candidate_dir(root, candidate_id)
    if not path.is_dir():
        print(f"review: candidate not found: {candidate_id}", file=sys.stderr)
        return 1
    shutil.rmtree(path)
    print(f"rejected {candidate_id}")
    return 0


def _review_gaps(settings: Settings, *, scope: str | None, limit: int) -> int:
    """Run the read-only knowledge-gap review and print its audit trail."""
    try:
        result = review_knowledge_gaps(settings, scope=scope, limit=limit)
    except Exception as exc:  # noqa: BLE001 - CLI must turn setup/agent failures into diagnostics
        print(f"review gaps: {exc}", file=sys.stderr)
        return 1

    print("knowledge-gap review audit:")
    print(f"  scope: {result.scope if result.scope is not None else '(all)'}")
    print(f"  coverage: {'partial' if result.partial else 'complete'}")
    print(f"  reviewed paths: {len(result.reviewed_paths)}")
    for path in result.reviewed_paths:
        print(f"    - {path}")
    print(f"  omitted notes: {result.omitted_count}")
    print("  read allowlist:")
    for path in result.read_allowlist:
        print(f"    - {path}")
    print(result.render_markdown())
    return 0


def _print_run_plan(settings: Settings, *, only: list[str], limit: int | None) -> None:
    """Print a no-write estimate for one pipeline run."""
    cfg = settings
    raw = cfg.raw_dir()
    wiki = cfg.wiki_dir()
    raw_uris = dedupe_raw_uris_for_wiki(wiki, _raw_file_relpaths(raw, exclude_dir=wiki))
    md_relpaths = sorted(rel for rel in raw_uris if rel.lower().endswith(".md"))
    selected = select_llm_compile_relpaths(md_relpaths, only=only, limit=limit)
    changed = selected
    if cfg.llm_compile:
        manifest = load_manifest(cfg.resolved_manifest_path())
        all_changed = changed_md_relpaths(
            raw,
            md_relpaths,
            manifest,
            incremental=cfg.llm_compile_incremental,
        )
        changed = select_llm_compile_relpaths(all_changed, only=only, limit=limit)

    print("run plan (no files or API calls will be made):")
    print(f"  raw files: {len(raw_uris)}")
    print(f"  markdown concepts: {len(md_relpaths)}")
    print(f"  LLM authoring: {'on' if cfg.llm_compile else 'off'}")
    print(f"  selected authoring files: {len(selected)}")
    print(f"  LLM author calls: {len(changed) if cfg.llm_compile else 0}")
    print(f"  semantic links: {'on' if cfg.semantic_links else 'off'}")
    if cfg.semantic_links:
        manifest = load_manifest(cfg.resolved_manifest_path())
        print(f"  semantic cache entries: {len(manifest.get('semantic_edges') or {})}")
    print(f"  QMD refresh: {'on' if cfg.qmd_refresh else 'off'}")
    print(f"  lint: {'on' if cfg.lint_on_run else 'off'}")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the wiki pipeline."""
    parser = argparse.ArgumentParser(
        prog="wiki-langgraph",
        description="Ingest → compile wiki (.md) → index (QMD refresh when enabled) → lint.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the full graph once")
    run_p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print step log lines",
    )
    run_p.add_argument(
        "--plan",
        action="store_true",
        help="Print the selected files and estimated AI work without writing or calling APIs",
    )
    run_p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="GLOB",
        help="Limit LLM authoring to matching raw paths; repeat for multiple patterns",
    )
    run_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap the number of LLM-authored files for this run",
    )

    agent_p = sub.add_parser(
        "agent",
        help="Inspect, plan, run the graph once, and verify the result",
    )
    agent_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and print the bounded plan without writing or calling APIs",
    )
    agent_p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="GLOB",
        help="Limit LLM authoring to matching raw paths; repeat for multiple patterns",
    )
    agent_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap the number of LLM-authored files for this agent step",
    )
    agent_p.add_argument(
        "--max-iterations",
        type=int,
        default=2,
        metavar="N",
        help="Maximum inspect/act/verify iterations (default: 2)",
    )
    agent_p.add_argument(
        "--deep-review",
        action="store_true",
        help="Opt in to a read-only DeepAgent review of queued candidates",
    )
    agent_p.add_argument(
        "--candidate",
        action="append",
        default=[],
        metavar="ID",
        help="Review a specific queued candidate; repeat to select multiple",
    )
    agent_p.add_argument(
        "--review-limit",
        type=int,
        default=3,
        metavar="N",
        help="Maximum candidates sent to DeepAgent review (default: 3)",
    )

    sub.add_parser("version", help="Print version")

    query_p = sub.add_parser("query", help="Ask a question over the compiled wiki")
    query_p.add_argument("question", help="Question to answer using compiled wiki context")
    query_p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of compiled wiki notes to include as context (default: 5)",
    )
    query_p.add_argument(
        "--save",
        action="store_true",
        help="Save the answer as a raw markdown note under Queries/",
    )

    research_p = sub.add_parser("research", help="Synthesize a research brief over the compiled wiki")
    research_p.add_argument("question", help="Research question to investigate using compiled wiki context")
    research_p.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of compiled wiki notes to include as context (default: 8)",
    )
    research_p.add_argument(
        "--save",
        action="store_true",
        help="Save the brief as a raw markdown note under Research/",
    )

    eval_p = sub.add_parser("eval", help="Run the research evaluation dataset through Langfuse")
    eval_p.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/research_dataset.json"),
        help="Local evaluation dataset JSON path (default: evals/research_dataset.json)",
    )
    eval_p.add_argument(
        "--name",
        default=None,
        help="Override the Langfuse experiment name",
    )
    eval_p.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum concurrent dataset items (default: 1)",
    )
    eval_p.add_argument(
        "--local",
        action="store_true",
        help="Run the local JSON items instead of fetching the hosted Langfuse dataset",
    )
    eval_p.add_argument(
        "--corpus-root",
        type=Path,
        default=Path("."),
        help="Project root containing the raw and compiled corpus (default: current directory)",
    )

    agent_eval_p = sub.add_parser("agent-eval", help="Run bounded agent fixture evaluations through Langfuse")
    agent_eval_p.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/agent_dataset.json"),
        help="Agent evaluation dataset JSON path (default: evals/agent_dataset.json)",
    )
    agent_eval_p.add_argument("--name", default=None, help="Override the Langfuse experiment name")
    agent_eval_p.add_argument("--max-concurrency", type=int, default=1)
    agent_eval_p.add_argument("--corpus-root", type=Path, default=Path("."))

    review_p = sub.add_parser(
        "review",
        help="Inspect compile candidates or run a read-only editorial knowledge-gap review",
    )
    review_sub = review_p.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("list", help="List pending LLM compile candidates")
    review_show = review_sub.add_parser("show", help="Show one pending candidate")
    review_show.add_argument("candidate_id")
    review_approve = review_sub.add_parser("approve", help="Approve one pending candidate")
    review_approve.add_argument("candidate_id")
    review_reject = review_sub.add_parser("reject", help="Reject one pending candidate")
    review_reject.add_argument("candidate_id")
    review_gaps = review_sub.add_parser(
        "gaps",
        help="Run a bounded, read-only review for missing or weakly connected knowledge",
    )
    review_gaps.add_argument(
        "scope",
        nargs="?",
        help="Optional Markdown file or directory relative to the raw and wiki roots",
    )
    review_gaps.add_argument(
        "--limit",
        type=int,
        default=24,
        metavar="N",
        help="Maximum logical notes to review (default: 24; range: 1-100)",
    )

    lint_p = sub.add_parser("lint", help="Check raw markdown for unresolved wikilinks and wiki Index drift")
    lint_p.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 if any warnings are reported (not only errors)",
    )
    lint_p.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Rewrite raw .md: fuzzy-match unresolved [[wikilinks]] to catalog labels, "
            "then strip remaining links to plain text (use --fix-mode to change)"
        ),
    )
    lint_p.add_argument(
        "--fix-mode",
        choices=("auto", "strip", "rewrite"),
        default="auto",
        help="auto: fuzzy then strip; strip: plain text only; rewrite: fuzzy only (leave unfixable links)",
    )
    lint_p.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fix, print planned edits without writing files",
    )
    lint_p.add_argument(
        "--fuzzy-cutoff",
        type=float,
        default=0.84,
        metavar="0.0-1.0",
        help="Minimum similarity for a unique fuzzy wikilink match (default: 0.84)",
    )

    args = parser.parse_args(argv)

    if args.command == "version":
        from wiki_langgraph import __version__

        print(__version__)
        return 0

    if args.command == "run":
        if args.limit is not None and args.limit < 1:
            parser.error("run --limit must be at least 1")
        settings = load_settings()
        if args.plan:
            _print_run_plan(settings, only=list(args.only), limit=args.limit)
            return 0
        configure_logging(settings)
        log = logging.getLogger("wiki_langgraph.cli")
        run_kwargs: dict[str, object] = {}
        if args.only:
            run_kwargs["llm_only"] = list(args.only)
        if args.limit is not None:
            run_kwargs["llm_limit"] = args.limit
        state = run_once(settings=settings, **run_kwargs)
        done = (
            f"done: raw_files={len(state.get('raw_uris', []))} "
            f"index_md_written={state.get('index_md_written')}"
        )
        last_error = state.get("last_error")
        if last_error:
            print(last_error, file=sys.stderr)
            for line in state.get("step_log", []):
                print(line, file=sys.stderr)
            log.error("pipeline failed: %s", last_error)
            return 1
        if args.verbose:
            for line in state.get("step_log", []):
                print(line)
        print(done)
        log.info(done)
        return 0

    if args.command == "agent":
        if args.limit is not None and args.limit < 1:
            parser.error("agent --limit must be at least 1")
        if args.max_iterations < 1:
            parser.error("agent --max-iterations must be at least 1")
        if args.review_limit < 1:
            parser.error("agent --review-limit must be at least 1")
        settings = load_settings()
        only = list(args.only)
        if not args.dry_run:
            configure_logging(settings)
        for iteration in range(1, args.max_iterations + 1):
            inspection = inspect_workspace(settings, only=only, limit=args.limit)
            plan = make_plan(inspection)
            print(f"agent iteration {iteration}/{args.max_iterations}")
            for line in format_plan(plan, dry_run=args.dry_run):
                print(line)
            if args.dry_run or plan.action == "stop":
                return 0

            run_kwargs: dict[str, object] = {"lint_strict": False}
            if only:
                run_kwargs["llm_only"] = only
            if args.limit is not None:
                run_kwargs["llm_limit"] = args.limit
            state = run_once(settings=settings, **run_kwargs)
            for line in verification_lines(state):
                print(line, file=sys.stderr if state.get("last_error") else sys.stdout)
            if args.deep_review and not state.get("last_error"):
                review = review_candidates(
                    settings,
                    candidate_ids=list(args.candidate),
                    limit=args.review_limit,
                )
                print(f"deep-review: candidates={len(review.candidate_ids)}")
                print(review.report)
            post_inspection = inspect_workspace(settings, only=only, limit=args.limit)
            next_plan = replan_after_verification(state, post_inspection)
            for line in replan_lines(next_plan, iteration=iteration, max_iterations=args.max_iterations):
                print(line)
            if state.get("last_error"):
                return 1
            if next_plan.action in {"stop", "stop_for_review"}:
                return 0
            if iteration == args.max_iterations:
                print("replan: iteration budget exhausted; stopping for review")
                return 0
        return 0

    if args.command == "query":
        settings = load_settings()
        configure_logging(settings)
        result = answer_query(args.question, settings=settings, top_k=max(1, args.top_k))
        print(result.answer)
        print("\nSources:")
        if result.sources:
            for source in result.sources:
                print(f"- {source.relpath} (score={source.score})")
        else:
            print("- none")
        if args.save:
            saved = save_query_answer(
                question=result.question,
                answer=result.answer,
                source_relpaths=[source.relpath for source in result.sources],
                settings=settings,
            )
            print(f"\nsaved: {saved}")
        return 0

    if args.command == "research":
        settings = load_settings()
        configure_logging(settings)
        result = research_query(args.question, settings=settings, top_k=max(1, args.top_k))
        print(result.answer)
        print("\nSources:")
        if result.sources:
            for source in result.sources:
                print(f"- {source.relpath} (score={source.score})")
        else:
            print("- none")
        if args.save:
            saved = save_research_brief(
                question=result.question,
                brief=result.answer,
                source_relpaths=[source.relpath for source in result.sources],
                settings=settings,
            )
            print(f"\nsaved: {saved}")
        return 0

    if args.command == "eval":
        if args.max_concurrency < 1:
            parser.error("eval --max-concurrency must be at least 1")
        corpus_root = args.corpus_root.resolve()
        settings = load_settings().model_copy(
            update={
                "project_root": corpus_root,
                "data_raw_dir": corpus_root / "data/raw",
                "data_wiki_dir": corpus_root / "data/wiki",
            }
        )
        configure_logging(settings)
        try:
            result = run_research_experiment(
                settings=settings,
                dataset_path=args.dataset,
                name=args.name,
                max_concurrency=args.max_concurrency,
                hosted=not args.local,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"eval failed: {exc}", file=sys.stderr)
            return 1
        formatter = getattr(result, "format", None)
        print(formatter() if callable(formatter) else result)
        return 0

    if args.command == "agent-eval":
        if args.max_concurrency < 1:
            parser.error("agent-eval --max-concurrency must be at least 1")
        corpus_root = args.corpus_root.resolve()
        settings = load_settings().model_copy(
            update={
                "project_root": corpus_root,
                "data_raw_dir": corpus_root / "data/raw",
                "data_wiki_dir": corpus_root / "data/wiki",
            }
        )
        configure_logging(settings)
        try:
            result = run_agent_experiment(
                settings=settings,
                dataset_path=args.dataset,
                name=args.name,
                max_concurrency=args.max_concurrency,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"agent-eval failed: {exc}", file=sys.stderr)
            return 1
        formatter = getattr(result, "format", None)
        print(formatter() if callable(formatter) else result)
        return 0

    if args.command == "review":
        if args.review_command == "gaps":
            if not 1 <= args.limit <= 100:
                parser.error("review gaps --limit must be between 1 and 100")
            settings = load_settings()
            configure_logging(settings)
            return _review_gaps(settings, scope=args.scope, limit=args.limit)
        settings = load_settings()
        configure_logging(settings)
        root = candidate_root(settings.project_root)
        if args.review_command == "list":
            return _review_list(root)
        if args.review_command == "show":
            return _review_show(root, args.candidate_id)
        if args.review_command == "approve":
            return _review_approve(root, args.candidate_id)
        if args.review_command == "reject":
            return _review_reject(root, args.candidate_id)
        return 1

    if args.command == "lint":
        settings = load_settings()
        configure_logging(settings)
        raw = settings.raw_dir()
        wiki = settings.wiki_dir()
        uris = _raw_file_relpaths(raw)
        if args.fix:
            n_files, n_rep, fix_logs = fix_unresolved_wikilinks(
                raw,
                wiki,
                uris,
                mode=args.fix_mode,
                fuzzy_cutoff=args.fuzzy_cutoff,
                dry_run=args.dry_run,
            )
            for line in fix_logs:
                print(line)
            suffix = " (dry-run)" if args.dry_run else ""
            print(f"fix: {n_files} file(s), {n_rep} replacement(s){suffix}")
        report = run_lint(raw, wiki, uris, okf=settings.output_profile == "okf")
        for issue in report.issues:
            loc = f"{issue.path}: " if issue.path else ""
            detail = f" ({issue.detail})" if issue.detail else ""
            print(f"{issue.code} {loc}{issue.message}{detail}")
        if report.error_count:
            return 1
        if args.strict and report.warn_count:
            return 1
        return 0

    return 1


def _entry() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry()
