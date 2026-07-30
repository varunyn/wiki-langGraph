---
title: Langfuse Tracing and Evaluation Direction
note_type: session-research
project: wiki-langgraph
status: active
source_session_ids:
  - 019fb531-af9f-7b42-8cd3-3227285f7db3
tags:
  - session-research
  - langfuse
  - observability
  - evaluations
---

# Langfuse Tracing and Evaluation Direction

## Summary

The application now has end-to-end Langfuse tracing on the main graph and its LLM-backed paths. The next useful step is to turn research sessions into a repeatable evaluation dataset rather than evaluating isolated prompts.

## Decisions

- Work is isolated on `codex/langfuse-evals`.
- The local Langfuse server is the development observability backend.
- Tracing covers pipeline runs, queries, and research calls, with child spans for ingest, compile, index, and lint.
- Evaluation should begin with the `research` flow because it produces a structured answer that can be judged for evidence use, source coverage, and open-question quality.

## Implemented

- Added Langfuse SDK integration and environment-backed settings.
- Added root traces named `wiki.run`, `wiki.query`, and `wiki.research`.
- Added nested operation spans for `wiki.ingest`, `wiki.compile`, `wiki.index`, and `wiki.lint`.
- Wired LangChain callbacks into authoring, semantic-link, query, research, and deep-agent paths.
- Committed as `aa693e0 Add Langfuse v4 tracing`.

## Evidence

- A local smoke run produced a trace with the expected root and child spans in Langfuse.
- The observed trace used environment `development` and release `wiki-langgraph-local`.
- The repository dependency resolved to Langfuse SDK `4.14.2`; the local Docker Compose deployment is configured for Langfuse `4.1.0`.

## Open Questions

- Which research questions should form the first stable evaluation dataset?
- Which graders should be deterministic (source citation and required sections) versus model-based (usefulness and synthesis quality)?
- What score thresholds should block a future change?

## Suggested Follow-ups

1. Create a small dataset of representative research questions and expected evidence notes.
2. Run each example through `wiki.research` and attach scores to the resulting Langfuse observations.
3. Add evaluators for source grounding, source coverage, answer structure, and unresolved gaps.
4. Record dataset and evaluator identifiers in a project note so later sessions can reproduce the experiment.

## Related Notes

- [[Wiki Pipeline and OKF Evolution]]
- [[Bounded Agentic Workflow Architecture]]
- [[Operational Lessons for Session Notes]]
