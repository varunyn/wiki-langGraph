---
type: Note
---

# What state moves through the graph?

`WikiGraphState` carries the information that describes a single run. It includes the ingested raw paths, an append-only step log, whether `index.md` was regenerated, a final error signal, optional LLM selection controls, and lint counts.

Nodes return partial state updates. The `step_log` accumulates updates, while `raw_uris` is deliberately replaced with the newest file catalog to prevent accidental duplicate paths.

## Why this design

Small typed state makes a run inspectable and testable. Reducer behavior is explicit, so the graph does not depend on hidden mutable process state.

## Related

- [[Pipeline Topology]]
- [[Settings and Run Controls]]
- [[Reliability and Verification]]
