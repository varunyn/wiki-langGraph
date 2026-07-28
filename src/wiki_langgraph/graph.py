"""Build and compile the LangGraph workflow."""

from __future__ import annotations

import asyncio
from typing import cast

from langgraph.graph import END, START, StateGraph

from wiki_langgraph.config import Settings, load_settings
from wiki_langgraph.nodes import node_compile_wiki, node_index, node_ingest, node_lint
from wiki_langgraph.state import WikiGraphState


def _node_error_handler(node_name: str):
    """Return a graph-local fallback update for node failures."""

    def handler(state: WikiGraphState) -> dict[str, object]:
        step_log = list(state.get("step_log", []))
        msg = f"{node_name}: failed"
        return {"step_log": [*step_log, msg], "last_error": msg}

    return handler


def build_graph(settings: Settings | None = None):
    """Construct the ingest → compile → index → lint graph and return a compiled application."""
    cfg = settings or load_settings()

    async def ingest_wrapper(state: WikiGraphState) -> dict[str, object]:
        return await asyncio.to_thread(node_ingest, state, settings=cfg)

    async def compile_wrapper(state: WikiGraphState) -> dict[str, object]:
        return await asyncio.to_thread(node_compile_wiki, state, settings=cfg)

    async def index_wrapper(state: WikiGraphState) -> dict[str, object]:
        return await asyncio.to_thread(node_index, state, settings=cfg)

    async def lint_wrapper(state: WikiGraphState) -> dict[str, object]:
        return await asyncio.to_thread(node_lint, state, settings=cfg)

    workflow = StateGraph(WikiGraphState)
    workflow.add_node(
        "ingest",
        ingest_wrapper,
        timeout=cfg.graph_ingest_timeout_sec,
        error_handler=_node_error_handler("ingest"),
    )
    workflow.add_node(
        "compile_wiki",
        compile_wrapper,
        timeout=cfg.graph_compile_timeout_sec,
        error_handler=_node_error_handler("compile_wiki"),
    )
    workflow.add_node(
        "index",
        index_wrapper,
        timeout=cfg.graph_index_timeout_sec,
        error_handler=_node_error_handler("index"),
    )
    workflow.add_node(
        "lint",
        lint_wrapper,
        timeout=cfg.graph_lint_timeout_sec,
        error_handler=_node_error_handler("lint"),
    )
    workflow.add_edge(START, "ingest")
    workflow.add_edge("ingest", "compile_wiki")
    workflow.add_edge("compile_wiki", "index")
    workflow.add_edge("index", "lint")
    workflow.add_edge("lint", END)
    return workflow.compile()


def run_once(
    settings: Settings | None = None,
    *,
    llm_only: list[str] | None = None,
    llm_limit: int | None = None,
    lint_strict: bool | None = None,
) -> WikiGraphState:
    """Execute ingest → compile → index → lint once with optional LLM selection."""
    app = build_graph(settings=settings)
    initial: WikiGraphState = {
        "step_log": [],
        "raw_uris": [],
        "index_md_written": False,
        "last_error": None,
    }
    if llm_only:
        initial["llm_only"] = list(llm_only)
    if llm_limit is not None:
        initial["llm_limit"] = llm_limit
    if lint_strict is not None:
        initial["lint_strict"] = lint_strict
    return cast(WikiGraphState, asyncio.run(app.ainvoke(initial)))
