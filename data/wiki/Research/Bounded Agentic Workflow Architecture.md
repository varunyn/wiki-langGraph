---
title: Bounded Agentic Workflow Architecture
note_type: session-research
project: wiki-langgraph
status: established
source_session_ids:
- 019fa6ae-99fb-7b01-ab29-51607e81719a
tags:
- session-research
- agents
- langgraph
- deep-agents
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-07-30T23:54:58Z'
modified: '2026-07-30T23:54:58Z'
created: '2026-07-30T23:06:51Z'
---
# Bounded Agentic Workflow Architecture

## Summary

The application separates predictable graph work from open-ended review work. LangGraph owns ingest, compile, index, lint, and the bounded controller; Deep Agents are opt-in workers for research and read-only review.

## Decisions

- The normal run stays deterministic and bounded.
- The agent loop follows inspect → plan → act → verify → replan, with a small iteration limit.
- Deep review is read-only, path-scoped, and never approves or rejects candidates automatically.
- Existing lint and verification findings should become useful evaluation signals rather than being hidden.

## Evidence

- `agent --dry-run` exposes the plan without writes or API calls.
- `--max-iterations` bounds automatic work.
- Deep review is opt-in and operates on selected candidates plus skills and memory.
- The architecture and tests document the boundary between LangGraph and Deep Agents.

## Open Questions

- Should research evaluation run inside the bounded agent loop or as a separate Langfuse experiment?
- Which verification failures should be recorded as trace scores versus ordinary run errors?

## Suggested Follow-ups

- Keep research experiments independent from automatic approval workflows.
- Attach the agent iteration count, verification result, and review status to traces when those fields are available.

## Related Notes

- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [Research/Agent Evaluation Fixtures and Findings](Agent%20Evaluation%20Fixtures%20and%20Findings.md)
- [Research/Langfuse Evaluation Baseline and Trace Findings](Langfuse%20Evaluation%20Baseline%20and%20Trace%20Findings.md)
- [Research/Langfuse Tracing and Evaluation Direction](Langfuse%20Tracing%20and%20Evaluation%20Direction.md)
- [Research/Operational Lessons for Session Notes](Operational%20Lessons%20for%20Session%20Notes.md)
- [Research/Research Brief - Session Notes to Langfuse Evals](Research%20Brief%20-%20Session%20Notes%20to%20Langfuse%20Evals.md)
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)

<!-- /wiki-langgraph backlinks -->
