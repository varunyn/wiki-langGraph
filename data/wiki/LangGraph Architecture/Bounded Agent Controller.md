---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# Why is the bounded agent controller outside the main graph?

The main graph executes one deterministic compile pipeline. The optional `agent` command is a separate controller that inspects the corpus, manifest, and review queue; chooses a predefined safe action; runs the graph; verifies the result; and replans within a strict iteration limit.

It does not ask an LLM to invent shell commands or retry indefinitely. When it cannot identify a safe next action, it stops for review.

## Why this design

Keeping operational planning outside the compiler graph makes the core workflow easier to reason about, test, and run predictably. It adds bounded automation without making everyday compilation autonomous.

## Related

- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)
- [LangGraph Architecture/DeepAgent Review Role](DeepAgent%20Review%20Role.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [LangGraph Architecture/DeepAgent Review Role](DeepAgent%20Review%20Role.md)
- [LangGraph Architecture/README](README.md)
- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)

<!-- /wiki-langgraph backlinks -->
