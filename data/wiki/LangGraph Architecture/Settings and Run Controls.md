---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# How are settings kept separate from graph state?

The graph is built with a `Settings` object that supplies paths, timeouts, and feature flags to the node wrappers. Per-run controls such as LLM selection patterns, LLM limits, and lint strictness are placed in the initial graph state.

## Why this design

Settings describe how the system is configured to run. Graph state describes what happened during one run. Keeping them separate prevents node updates from accidentally changing runtime policy.

## Related

- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/Graph State Persistence](Graph%20State%20Persistence.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/Graph State Persistence](Graph%20State%20Persistence.md)
- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/README](README.md)

<!-- /wiki-langgraph backlinks -->
