"""LangGraph shared state for the wiki ingest → compile → index pipeline."""

import operator
from typing import Annotated, TypedDict


def _replace_raw_uris(previous: list[str], new: list[str]) -> list[str]:
    """Use the latest ``raw_uris`` list from a node (explicit replace, not append).

    LangGraph merges node updates into state; lists without a reducer default to
    replace — this keeps behavior obvious and avoids accidental concatenation.
    """

    return list(new)


class WikiGraphState(TypedDict, total=False):
    """State passed between graph nodes.

    Attributes:
        step_log: Append-only trace of node actions for debugging.
        raw_uris: Relative paths under the raw directory from recursive ingest.
        index_md_written: Whether compile regenerated ``index.md`` this run (when compile runs).
        last_error: Set when a node fails; downstream nodes may branch on this.
        llm_only: Optional glob patterns limiting LLM authoring; deterministic compile still sees all notes.
        llm_limit: Optional cap on the number of LLM-authored notes this run.
        lint_strict: Whether warnings should fail this graph run; agent runs set this false.
        lint_issue_count: Number of lint findings from the final lint node.
        lint_warning_count: Number of warning-level lint findings from the final lint node.
        lint_error_count: Number of error-level lint findings from the final lint node.
    """

    step_log: Annotated[list[str], operator.add]
    raw_uris: Annotated[list[str], _replace_raw_uris]
    index_md_written: bool
    last_error: str | None
    llm_only: list[str]
    llm_limit: int | None
    lint_strict: bool
    lint_issue_count: int
    lint_warning_count: int
    lint_error_count: int
