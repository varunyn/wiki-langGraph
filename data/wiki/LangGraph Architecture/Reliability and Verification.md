---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# How are failures and quality checks made visible?

If a graph node fails, its error handler adds a named failure message to the step log and sets `last_error`. The final lint node reports issue, warning, and error counts. A normal run exits with failure when the final state contains an error.

The bounded agent controller also reads this final state. It stops for human review when verification fails or warnings remain without a safe automatic fix.

## Why this design

A knowledge-base compiler should make partial success visible. Centralized final state gives the CLI and the bounded controller the same evidence for deciding whether the run was successful.

## Related

- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/Bounded Agent Controller](Bounded%20Agent%20Controller.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/Async Node Execution](Async%20Node%20Execution.md)
- [LangGraph Architecture/Bounded Agent Controller](Bounded%20Agent%20Controller.md)
- [LangGraph Architecture/DeepAgent Review Safety](DeepAgent%20Review%20Safety.md)
- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/Pipeline Topology](Pipeline%20Topology.md)
- [LangGraph Architecture/README](README.md)

<!-- /wiki-langgraph backlinks -->
