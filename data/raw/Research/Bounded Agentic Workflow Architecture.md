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

- [[Langfuse Tracing and Evaluation Direction]]
- [[Wiki Pipeline and OKF Evolution]]
- [[Operational Lessons for Session Notes]]
