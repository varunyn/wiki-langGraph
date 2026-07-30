---
title: Operational Lessons for Session Notes
note_type: session-research
project: wiki-langgraph
status: active
source_session_ids:
  - 019fa6ae-99fb-7b01-ab29-51607e81719a
  - 019fb531-af9f-7b42-8cd3-3227285f7db3
tags:
  - session-research
  - operations
  - configuration
  - testing
---

# Operational Lessons for Session Notes

## Summary

Session history is most useful when it records decisions, evidence, and follow-ups rather than transcript detail. These notes should be structured source material for compilation, retrieval, and evaluation.

## Working Rules

- Keep secrets and raw environment values out of notes; record configuration names and safe, non-secret endpoints only.
- Record commit identifiers, test commands, and observable outcomes when available.
- Keep `.env` precedence in mind: exported `WIKI_*` variables can override local settings and unexpectedly route runs to a different vault or model.
- Use isolated raw and wiki directories in tests.
- Prefer low-cost deterministic runs while curating the corpus; enable LLM authoring or semantic links deliberately.

## Evidence

- The project’s test guidance explicitly requires isolated `Settings` paths under `tmp_path`.
- Prior sessions found that local LLM defaults can be slow and that `WIKI_LLM_COMPILE=false`, `WIKI_SEMANTIC_LINKS=false`, and `WIKI_QMD_REFRESH=false` are the practical baseline.
- The tracing smoke test confirmed that operational metadata can be inspected in Langfuse without exposing credentials.

## Open Questions

- How much session context is enough for a useful research note?
- Should every note require a source session ID, or can manually curated domain notes omit one?

## Suggested Follow-ups

- Treat this folder as a curated research corpus, not a transcript archive.
- Add one structured note per meaningful decision or workstream, then compile before researching.

## Related Notes

- [[Langfuse Tracing and Evaluation Direction]]
- [[Wiki Pipeline and OKF Evolution]]
- [[Bounded Agentic Workflow Architecture]]
