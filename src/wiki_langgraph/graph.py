"""Build and compile the LangGraph workflow."""

from __future__ import annotations

from typing import cast

from langgraph.graph import END, START, StateGraph

from wiki_langgraph.config import Settings, load_settings
from wiki_langgraph.nodes import node_compile_wiki, node_index, node_ingest, node_lint
from wiki_langgraph.state import WikiGraphState


def build_graph(settings: Settings | None = None):
    """Construct the ingest → compile → index → lint graph and return a compiled application."""
    cfg = settings or load_settings()

    def ingest_wrapper(state: WikiGraphState) -> dict[str, object]:
        return node_ingest(state, settings=cfg)

    def compile_wrapper(state: WikiGraphState) -> dict[str, object]:
        return node_compile_wiki(state, settings=cfg)

    def index_wrapper(state: WikiGraphState) -> dict[str, object]:
        return node_index(state, settings=cfg)

    def lint_wrapper(state: WikiGraphState) -> dict[str, object]:
        return node_lint(state, settings=cfg)

    workflow = StateGraph(WikiGraphState)
    workflow.add_node("ingest", ingest_wrapper)
    workflow.add_node("compile_wiki", compile_wrapper)
    workflow.add_node("index", index_wrapper)
    workflow.add_node("lint", lint_wrapper)
    workflow.add_edge(START, "ingest")
    workflow.add_edge("ingest", "compile_wiki")
    workflow.add_edge("compile_wiki", "index")
    workflow.add_edge("index", "lint")
    workflow.add_edge("lint", END)
    return workflow.compile()


def run_once(settings: Settings | None = None) -> WikiGraphState:
    """Execute ingest → compile → index → lint once with empty initial state."""
    app = build_graph(settings=settings)
    initial: WikiGraphState = {
        "step_log": [],
        "raw_uris": [],
        "index_md_written": False,
        "last_error": None,
    }
    return cast(WikiGraphState, app.invoke(initial))
