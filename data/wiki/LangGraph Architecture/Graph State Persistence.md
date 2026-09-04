---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# Does the main LangGraph workflow persist checkpoints between runs?

No. The normal batch workflow runs with fresh in-memory graph state and does not configure a LangGraph checkpointer. It does not resume a partially completed compile after interruption.

Durable data has separate ownership: the manifest stores incremental hashes and semantic cache entries, while generated wiki notes and review candidates are stored as files.

## Why this design

Compilation is a short, repeatable batch operation. Explicit on-disk data is easier to inspect and restart than an implicit checkpointing layer for this workflow.

## Related

- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/Settings and Run Controls](Settings%20and%20Run%20Controls.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/README](README.md)
- [LangGraph Architecture/Settings and Run Controls](Settings%20and%20Run%20Controls.md)

<!-- /wiki-langgraph backlinks -->
