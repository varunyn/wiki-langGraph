---
type: Note
---

# Does the main LangGraph workflow persist checkpoints between runs?

No. The normal batch workflow runs with fresh in-memory graph state and does not configure a LangGraph checkpointer. It does not resume a partially completed compile after interruption.

Durable data has separate ownership: the manifest stores incremental hashes and semantic cache entries, while generated wiki notes and review candidates are stored as files.

## Why this design

Compilation is a short, repeatable batch operation. Explicit on-disk data is easier to inspect and restart than an implicit checkpointing layer for this workflow.

## Related

- [[Graph State]]
- [[Settings and Run Controls]]
