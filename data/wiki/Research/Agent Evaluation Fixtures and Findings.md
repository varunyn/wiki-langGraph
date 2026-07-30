---
title: Agent Evaluation Fixtures and Findings
note_type: session-research
project: wiki-langgraph
status: active
session_date: 2026-07-30
source_session_ids:
- 019fb531-af9f-7b42-8cd3-3227285f7db3
tags:
- session-research
- agents
- evaluations
- langgraph
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-07-30T23:54:58Z'
modified: '2026-07-30T23:54:58Z'
created: '2026-07-30T23:51:39Z'
---
# Agent Evaluation Fixtures and Findings

## Summary

Agent evaluation should exercise the real bounded inspect → plan → LangGraph → verify → replan sequence in isolated fixture workspaces. The first fixture set covers clean completion, warning-driven human review, and safe stopping on an empty workspace.

## Fixture Cases

- `clean`: two linked notes should compile, verify cleanly, and stop.
- `unresolved-link`: an unresolved wikilink should produce a warning and stop for review without an automatic fix.
- `empty`: no raw files should cause a safe stop before graph execution.

## Evaluation Dimensions

- Plan action matches the inspected workspace.
- Verification result is correct.
- Replan action stops safely or requests review as expected.
- Iteration count stays within the fixture’s bound.

## Architecture Boundary

The normal `agent` command uses the bounded LangGraph workflow. Deep Agents are only involved when `--deep-review` is explicitly enabled, and that review remains read-only and human-controlled. Agent evaluation should therefore start with the bounded path and add DeepAgent cases separately later.

## Related Notes

- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)
- [Research/Langfuse Evaluation Baseline and Trace Findings](Langfuse%20Evaluation%20Baseline%20and%20Trace%20Findings.md)
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)
<!-- wiki-langgraph backlinks -->
## Backlinks

Notes that link here (authored ``[[wikilinks]]``):

- [Sessions/2026-07-30 Langfuse Agent Evaluation Session](../Sessions/2026-07-30%20Langfuse%20Agent%20Evaluation%20Session.md)

<!-- /wiki-langgraph backlinks -->
