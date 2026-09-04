---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# What state moves through the graph?

`WikiGraphState` carries the information that describes a single run. It includes the ingested raw paths, an append-only step log, whether `index.md` was regenerated, a final error signal, optional LLM selection controls, and lint counts.

Nodes return partial state updates. The `step_log` accumulates updates, while `raw_uris` is deliberately replaced with the newest file catalog to prevent accidental duplicate paths.

## Why this design

Small typed state makes a run inspectable and testable. Reducer behavior is explicit, so the graph does not depend on hidden mutable process state.

## Related

- [LangGraph Architecture/Pipeline Topology](Pipeline%20Topology.md)
- [LangGraph Architecture/Settings and Run Controls](Settings%20and%20Run%20Controls.md)
- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/Graph State Persistence](Graph%20State%20Persistence.md)
- [LangGraph Architecture/Pipeline Topology](Pipeline%20Topology.md)
- [LangGraph Architecture/README](README.md)
- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)
- [LangGraph Architecture/Settings and Run Controls](Settings%20and%20Run%20Controls.md)

<!-- /wiki-langgraph backlinks -->
