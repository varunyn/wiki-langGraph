---
title: Research Brief - Session Notes to Langfuse Evals
note_type: research-brief
project: wiki-langgraph
status: proposed
source_session_ids:
- 019fb531-af9f-7b42-8cd3-3227285f7db3
- 019fa6ae-99fb-7b01-ab29-51607e81719a
tags:
- research
- langfuse
- evaluations
- session-research
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-07-30T23:54:58Z'
modified: '2026-07-30T23:54:58Z'
created: '2026-07-30T23:08:09Z'
---
# Research Brief

## Summary

Structured session notes are a strong first evaluation corpus because they preserve the application’s decisions, implementation evidence, and unresolved questions without carrying raw transcript noise. The recommended first experiment is a small Langfuse dataset for `wiki.research`, where each item contains a research question, relevant source-note titles, and expected evidence-backed themes.

## Key Findings

1. **Start with research quality, not end-to-end workflow quality.** The application already emits `wiki.research` traces and retrieves compiled notes, so the first evaluation can focus on synthesis quality while keeping ingestion and compilation deterministic.
2. **Use structured notes as the source corpus.** Each note should include `note_type`, project/status metadata, source session IDs, decisions, evidence, open questions, and follow-ups. This makes retrieval and grading explainable.
3. **Make source grounding a first-class score.** A useful answer must cite exact wiki note titles and distinguish evidence-backed findings from gaps. This follows the existing research prompt contract and the project’s separate authored/semantic-link provenance model.
4. **Combine deterministic and model-based graders.** Deterministic checks can verify required sections, source-note links, and whether cited notes were retrieved. A model-based grader can assess synthesis usefulness, completeness, and whether the answer respects uncertainty.
5. **Keep agent review separate from evaluation approval.** The bounded agent and DeepAgent review flows are intentionally scoped and human-controlled. Evaluation scores should inform development and release decisions without silently approving content.

## Proposed Dataset Shape

Each dataset item should contain:

- `input.question`: a realistic research question about the project.
- `input.source_notes`: the note titles expected to provide evidence.
- `expected.themes`: two to five claims or themes a good answer should cover.
- `expected.gaps`: known limitations the answer should acknowledge.
- `metadata`: corpus version, note type, and source session IDs.

## Initial Evaluation Dimensions

- **Grounding:** cited notes support the claims made.
- **Coverage:** expected themes are addressed.
- **Structure:** summary, findings, sources, related concepts, open questions, and follow-ups are present.
- **Usefulness:** the answer turns session history into an actionable next step.
- **Uncertainty:** missing evidence and unresolved decisions are stated rather than invented.

## Evidence

- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md) records the implemented trace hierarchy, local smoke-test evidence, and the proposed first experiment.
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md) establishes raw notes as source material and preserves provenance boundaries.
- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md) establishes that review and approval remain bounded and human-controlled.
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md) defines the privacy, configuration, and reproducibility rules for the corpus.

## Open Questions

- Which five to ten questions best represent real research work in this application?
- Should expected themes be authored manually first, or generated and then reviewed?
- What minimum grounding and coverage scores should be required before changing the research prompt or retrieval logic?
- Which supported chat model should be configured for the local research run?

## Suggested Follow-ups

1. Configure a supported model for the OpenAI-compatible research endpoint; the current endpoint rejected `DeepSeek V4 Flash` as unsupported.
2. Create the first Langfuse dataset from this note set, keeping corpus version and source session IDs in metadata.
3. Run each item through `wiki.research`, attach evaluator scores, and inspect failed examples in the Langfuse UI.
4. Add a regression test for deterministic structure and source-link presence before tuning model-based graders.
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [Research/Langfuse Evaluation Baseline and Trace Findings](Langfuse%20Evaluation%20Baseline%20and%20Trace%20Findings.md)

<!-- /wiki-langgraph backlinks -->
