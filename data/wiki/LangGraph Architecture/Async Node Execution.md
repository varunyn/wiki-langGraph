---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# How does the graph run synchronous file work asynchronously?

The graph is invoked asynchronously with `ainvoke`. Each LangGraph node is an async wrapper around an existing synchronous file-processing function. The wrapper uses `asyncio.to_thread` to run that work in a worker thread and returns the resulting partial state update to the graph.

## Why this design

The project keeps stable compiler logic as ordinary synchronous Python while LangGraph provides async orchestration, per-node timeouts, and graph-local error handling. It avoids a broad rewrite solely to make file processing async.

## Related

- [LangGraph Architecture/Pipeline Topology](Pipeline%20Topology.md)
- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/README](README.md)

<!-- /wiki-langgraph backlinks -->
