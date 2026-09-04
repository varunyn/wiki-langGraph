---
title: 2026-07-30 Langfuse Agent Evaluation Session
note_type: session-log
project: wiki-langgraph
session_date: 2026-07-30
status: active
tags:
- session-log
- langfuse
- agent-evaluation
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T13:36:31Z'
modified: '2026-09-04T13:36:31Z'
created: '2026-07-30T23:54:58Z'
---
# 2026-07-30 Langfuse Agent Evaluation Session

## What happened

- Confirmed that `research` uses wiki retrieval plus one configured model call; it does not invoke an agent.
- Confirmed that normal `agent` uses the bounded LangGraph workflow.
- Confirmed that Deep Agents are only used by the optional `agent --deep-review` path.
- Added a hosted Langfuse dataset for bounded-agent evaluation.
- Added three agent fixtures: clean completion, unresolved-link review, and empty-workspace safe stop.
- Added the `wiki-langgraph agent-eval` command.
- Ran the three agent cases through Langfuse successfully.

## Commands used

```bash
uv run wiki-langgraph agent-eval
uv run wiki-langgraph eval
uv run wiki-langgraph research "Compare the application’s research flow with its evaluation workflow"
```

## Results

- Agent plan quality: `1.000`
- Agent verification: `1.000`
- Agent safe stop: `1.000`
- Agent boundedness: `1.000`
- Main corpus compile: 7 notes, lint clean.

## Problems encountered

- The first agent dataset validation assumed research fields such as `themes` and `gaps`; the shared validator was updated to support agent expectations.
- Calling the synchronous LangGraph runner inside Langfuse’s async experiment loop required moving the graph call to a worker thread.
- Generated research output was removed from the raw/wiki corpus so future research evaluations do not retrieve their own previous answer.

## Follow-up

- Add DeepAgent review cases separately after the bounded agent baseline is stable.
- Keep generated research and experiment outputs outside `data/raw/` source notes.

## Related notes

- [Research/Agent Evaluation Fixtures and Findings](../Research/Agent%20Evaluation%20Fixtures%20and%20Findings.md)
- [Research/Langfuse Evaluation Baseline and Trace Findings](../Research/Langfuse%20Evaluation%20Baseline%20and%20Trace%20Findings.md)