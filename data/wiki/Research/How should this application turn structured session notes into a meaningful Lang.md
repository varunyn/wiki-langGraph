---
title: How should this application turn structured session notes into a meaningful Langfuse evaluation dataset for research
  quality?
tags:
- research
- ai
source_question: How should this application turn structured session notes into a meaningful Langfuse evaluation dataset for
  research quality?
created: '2026-07-30T23:11:00Z'
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-07-30T23:38:30Z'
modified: '2026-07-30T23:38:30Z'
---
> Source question: How should this application turn structured session notes into a meaningful Langfuse evaluation dataset for research quality?

# Research Brief

## Summary

The application should treat structured session notes as the primary evaluation corpus for the `wiki.research` flow based on a synthesis of the existing tracing infrastructure, note schema, and architectural boundaries. The recommended approach is to build a small, curated Langfuse dataset where each item tests the model’s ability to synthesize evidence-backed findings from specific source-note titles while explicitly acknowledging unresolved gaps. Evaluation must combine deterministic checks for grounding and structure with model-based grading for synthesis quality, and it must remain strictly separate from automated approval workflows. The existing Langfuse tracing on `wiki.research` and the established structured-note conventions make this experiment immediately feasible.

## Key Findings

1. **The structured-note corpus is evaluation-ready.** Session notes already preserve `note_type`, decisions, evidence, open questions, and source session IDs without raw transcript noise. This aligns directly with the proposed dataset shape of `input.question`, `input.source_notes`, and `expected.themes` from `[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`.

2. **Evaluation should target research synthesis, not deterministic ingestion.** Langfuse tracing covers `wiki.research` with child spans for ingest, compile, index, and lint. The first evaluation should focus on synthesis quality because ingestion and compilation are already deterministic and well-tested (`[Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)`, `[Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)`).

3. **Source grounding must be the first-class evaluation metric.** The existing research prompt contract requires citing exact wiki note titles and distinguishing evidence-backed findings from gaps. This matches the project’s provenance model, which separates authored `[[wikilinks]]` from semantic suggestions (`[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`, `[Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)`).

4. **A dual grading strategy is required.** Deterministic graders can verify required sections (summary, findings, sources, open questions) and whether cited notes were in the retrieval context. Model-based graders are necessary to assess synthesis usefulness, coverage of expected themes, and whether the answer properly handles uncertainty (`[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`, `[Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)`).

5. **Evaluation scores must inform development without silently approving content.** The bounded agent and DeepAgent review flows are intentionally scoped and human-controlled. Evaluation must remain an experimental feedback mechanism, not an automatic approval gate (`[Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)`, `[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`).

6. **The operational baseline is low-cost and controllable.** The recommended practice during curation is to run with `WIKI_LLM_COMPILE=false`, `WIKI_SEMANTIC_LINKS=false`, and `WIKI_QMD_REFRESH=false`. Evaluation runs can be efficiently iterated against a stable curated corpus without full pipeline enrichment (`[Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)`).

## Source Notes

- `[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`
- `[Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)`
- `[Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)`
- `[Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)`
- `[Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)`

## Related Concepts

- `[Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)` – Defines why research experiments must be independent from automatic approval workflows and establishes the bounded vs. deep review boundary.
- `[Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)` – Provides the deterministic compiler baseline, the authored vs. semantic provenance model, and the schema question for `note_type` in OKF metadata.
- `[Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)` – Establishes the curation rules for session notes (isolated directories, minimal LLM defaults, safe operational metadata) that ensure the evaluation corpus is reliable.

## Open Questions

1. **Which specific research questions should form the first stable evaluation dataset?** Both `[Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)` and `[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)` identify this as the immediate blocking question.
2. **What score thresholds should block a future change?** The project has not yet established pass/fail criteria for grounding, coverage, or structure scores (`[Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)`).
3. **Should every session note require a source session ID to be a valid corpus item?** `[Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)` raises this explicitly, noting that manually curated domain notes may legitimately omit one.
4. **Should research evaluation run inside the bounded agent loop or as a separate Langfuse experiment?** `[Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)` frames this as an unresolved architectural decision.
5. **Should session notes use a dedicated `note_type` in the OKF metadata schema?** `[Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)` explicitly flags this as an open question for making evaluable notes identifiable at compile time.
6. **What is the optimal initial split between deterministic and model-based graders?** The balance between cheap structural checks and expensive synthesis scoring remains undefined (`[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`).

## Suggested Follow-ups

1. **Create the small evaluation dataset** as proposed in `[Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)`: draft 5–10 realistic research questions paired with expected source-note titles, evidence-backed themes, and known gaps.
2. **Implement the dual evaluators** on the `codex/langfuse-evals` branch: start with deterministic graders (required sections present, citation anchoring) then add a model-based grader for synthesis usefulness and uncertainty handling.
3. **Run `wiki.research` against the dataset** in the local Langfuse development environment, attach the evaluators to the resulting observations, and record dataset and evaluator identifiers in a project note for reproducibility.
4. **Define preliminary score thresholds** based on initial run results, distinguishing between “needs investigation” scores and “blocking” scores for development gates.
5. **Add a small fixture corpus of structured session notes** to the test suite and compile it in CI to ensure the deterministic structure required for evaluation items remains stable across pipeline changes.

## Sources

- [Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)
- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)
- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)