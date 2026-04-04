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
        index_md_written: Whether compile regenerated ``Index.md`` this run (when compile runs).
        last_error: Set when a node fails; downstream nodes may branch on this.
    """

    step_log: Annotated[list[str], operator.add]
    raw_uris: Annotated[list[str], _replace_raw_uris]
    index_md_written: bool
    last_error: str | None
