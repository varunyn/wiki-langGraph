"""CLI entrypoint for running the LangGraph pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import NoReturn

from wiki_langgraph.config import load_settings
from wiki_langgraph.graph import run_once
from wiki_langgraph.lint import fix_unresolved_wikilinks, run_lint
from wiki_langgraph.logging_config import configure_logging
from wiki_langgraph.manifest import load_manifest, save_manifest
from wiki_langgraph.nodes import _raw_file_relpaths
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

    review_p = sub.add_parser("review", help="Inspect and resolve LLM compile review candidates")
    review_sub = review_p.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("list", help="List pending LLM compile candidates")
    review_show = review_sub.add_parser("show", help="Show one pending candidate")
    review_show.add_argument("candidate_id")
    review_approve = review_sub.add_parser("approve", help="Approve one pending candidate")
    review_approve.add_argument("candidate_id")
    review_reject = review_sub.add_parser("reject", help="Reject one pending candidate")
    review_reject.add_argument("candidate_id")

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
        settings = load_settings()
        configure_logging(settings)
        log = logging.getLogger("wiki_langgraph.cli")
        state = run_once(settings=settings)
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

    if args.command == "review":
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
