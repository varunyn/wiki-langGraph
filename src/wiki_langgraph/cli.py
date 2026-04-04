"""CLI entrypoint for running the LangGraph pipeline."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

import logging

from wiki_langgraph.config import load_settings
from wiki_langgraph.graph import run_once
from wiki_langgraph.lint import fix_unresolved_wikilinks, run_lint
from wiki_langgraph.logging_config import configure_logging
from wiki_langgraph.nodes import _raw_file_relpaths


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
        if args.verbose:
            for line in state.get("step_log", []):
                print(line)
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
        print(done)
        log.info(done)
        return 0

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
        report = run_lint(raw, wiki, uris)
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
