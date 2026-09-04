---
title: Langfuse Evaluation Baseline and Trace Findings
note_type: session-research
project: wiki-langgraph
status: active
session_date: 2026-07-30
source_session_ids:
  - 019fb531-af9f-7b42-8cd3-3227285f7db3
tags:
  - session-research
  - langfuse
  - evaluations
  - traces
---

# Langfuse Evaluation Baseline and Trace Findings

## Summary

The first hosted Langfuse evaluation is working end to end. The application now publishes a five-item research dataset, fetches that hosted dataset, runs each question through `wiki.research`, and records evaluator observations and scores in a linked Langfuse dataset run.

## Work Completed

- Installed `langfuse-cli` globally. The package is `langfuse-cli@0.0.12`; its executable is `langfuse` under the Hermes-managed Node prefix.
- Published dataset `wiki-langgraph-research-v1` to the local Langfuse project with five active items.
- Added hosted dataset support to `wiki-langgraph eval`; the local JSON fixture remains available with `--local`.
- Added `--corpus-root` so evaluation cannot accidentally retrieve notes from an unrelated `.env`-configured vault.
- Added deterministic evaluators for structure, grounding, theme coverage, and uncertainty.

## Baseline Experiment

- Experiment: `wiki-langgraph-research-v1-repo-corpus`
- Dataset run: [Langfuse dataset run](http://localhost:3300/project/rag-app/datasets/cms84xzd70008po07v5qmeh5o/runs/561214b1-e941-4792-aa54-d6446af6ad42)
- Dataset item count: 5
- Concurrency: 1
- Environment: `development`
- Release: `wiki-langgraph-local`

### Scores

- Grounding: `0.700`
- Theme coverage: `1.000`
- Uncertainty: `1.000`
- Structure: `0.967`

## Trace Findings

The corrected experiment trace has the expected hierarchy:

1. Langfuse experiment item task.
2. Application `wiki.research` observation.
3. Nested model generation.
4. Evaluator observations and scores.

The application research observation contains the question, generated brief, and retrieved source paths. The corrected run retrieved the repository’s `Research/` notes, including the expected session-research notes and the generated research brief.

Research questions do not invoke an agent. The current flow is lexical wiki retrieval followed by one configured chat-model synthesis call. Agent behavior is separate and opt-in through the `agent` command and DeepAgent review paths.

## Operational Findings

- The Langfuse CLI can list datasets, dataset items, observations, and runs.
- The installed CLI could not create resources against this local server because its generated schema handling failed on `nullable` fields. The Langfuse Python SDK was used as a fallback for dataset creation and item upload; CLI verification succeeded afterward.
- An earlier baseline accidentally loaded an external vault from `.env`, producing unrelated research content. That run is retained as a diagnostic trace and must not be used as an evaluation baseline.
- A prior trace records the rejected display-name model `DeepSeek V4 Flash`; the corrected model ID is `deepseek-v4-flash`.
- Full tests currently report 156 passing and three environment-sensitive failures involving DeepAgents and `.env` timeout values. Focused evaluation tests and Ruff pass.

## Open Questions

- Is the grounding score of `0.700` caused by the evaluator’s source-title matching, or does it correctly identify incomplete source coverage in some outputs?
- Should the generated research brief itself be excluded from retrieval to avoid self-referential answers?
- What minimum grounding, structure, and theme-coverage thresholds should block a change?
- Should model metadata be promoted from nested generation observations to the application-level `wiki.research` span for easier filtering?

## Related Notes

- [[Langfuse Tracing and Evaluation Direction]]
- [[Research Brief - Session Notes to Langfuse Evals]]
- [[Operational Lessons for Session Notes]]
- [[Bounded Agentic Workflow Architecture]]
