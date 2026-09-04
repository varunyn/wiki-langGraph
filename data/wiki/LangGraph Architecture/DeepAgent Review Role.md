---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# Where do Deep Agents fit in the application?

Deep Agents are not part of the normal `run` pipeline or ordinary bounded `agent` loop. They are opt-in, read-only workers used by two separate review paths.

`agent --deep-review` reads selected queued LLM candidates and returns concise approval, revision, or rejection recommendations for a human reviewer. It does not make the final decision.

`review gaps [scope] [--limit N]` inspects a deterministic, bounded selection of raw and compiled notes. It returns structured editorial findings for missing concepts, missing overviews, weak connections, possible duplication or conflict, and missing raw/wiki counterparts. The report discloses partial coverage and the exact reviewed paths.

## Why this design

Agentic reasoning is most useful where editorial judgment and context matter. Keeping both review paths outside routine compilation preserves predictable, inexpensive batch runs while letting each path enforce its own scope and output contract.

## Related

- [LangGraph Architecture/Bounded Agent Controller](Bounded%20Agent%20Controller.md)
- [LangGraph Architecture/DeepAgent Review Safety](DeepAgent%20Review%20Safety.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/Bounded Agent Controller](Bounded%20Agent%20Controller.md)
- [LangGraph Architecture/DeepAgent Review Safety](DeepAgent%20Review%20Safety.md)
- [LangGraph Architecture/README](README.md)

<!-- /wiki-langgraph backlinks -->
