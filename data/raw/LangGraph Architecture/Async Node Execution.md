---
type: Note
---

# How does the graph run synchronous file work asynchronously?

The graph is invoked asynchronously with `ainvoke`. Each LangGraph node is an async wrapper around an existing synchronous file-processing function. The wrapper uses `asyncio.to_thread` to run that work in a worker thread and returns the resulting partial state update to the graph.

## Why this design

The project keeps stable compiler logic as ordinary synchronous Python while LangGraph provides async orchestration, per-node timeouts, and graph-local error handling. It avoids a broad rewrite solely to make file processing async.

## Related

- [[Pipeline Topology]]
- [[Reliability and Verification]]
