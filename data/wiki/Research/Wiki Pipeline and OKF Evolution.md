---
title: Wiki Pipeline and OKF Evolution
note_type: session-research
project: wiki-langgraph
status: established
source_session_ids:
- 019fa6ae-99fb-7b01-ab29-51607e81719a
tags:
- session-research
- architecture
- okf
- compiler
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-07-30T23:54:58Z'
modified: '2026-07-30T23:54:58Z'
created: '2026-07-30T23:06:51Z'
---
# Wiki Pipeline and OKF Evolution

## Summary

The repository is a deterministic markdown-to-wiki compiler with optional AI enrichment. Recent work aligned the compiler with OKF v0.2 and preserved a clear distinction between authored links and semantic suggestions.

## Decisions

- Raw markdown remains the source of truth; `data/wiki` is compiled output.
- Ingest is recursive and source-relative links are preserved.
- Reserved generated files such as `index.md` and `log.md` are excluded from concept and graph calculations.
- Explicit authored wikilinks drive backlinks. Semantic suggestions remain a separate provenance layer.
- The minimal path keeps LLM compile, semantic links, and QMD refresh disabled.

## Implemented

- Added OKF v0.2 metadata and compiler behavior.
- Added support for nested source-relative markdown links.
- Updated index and graph generation to exclude reserved files.
- Preserved incremental manifest behavior for optional LLM and semantic work.
- Recorded the OKF alignment in commit `6422bc8 fix: align compiler with OKF v0.2`.

## Evidence

- The repository guide requires `index.md` to be regenerated on every compile.
- The graph, linking, lint, manifest, and configuration tests cover the relevant behavior.
- The deterministic pipeline is suitable as the baseline against which AI-assisted changes can be evaluated.

## Open Questions

- Should session notes use a dedicated `note_type` in the OKF metadata schema?
- Which generated sections are most valuable as evaluator input: backlinks, semantic suggestions, or lint findings?

## Suggested Follow-ups

- Add a small fixture corpus of structured session notes and compile it in CI.
- Include source-note paths and lint status in research evaluation context.

## Related Notes

- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)
- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [Research/Agent Evaluation Fixtures and Findings](Agent%20Evaluation%20Fixtures%20and%20Findings.md)
- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)
- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)
- [Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)

<!-- /wiki-langgraph backlinks -->
