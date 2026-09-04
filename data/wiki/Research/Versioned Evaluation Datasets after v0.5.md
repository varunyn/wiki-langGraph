---
title: Versioned Evaluation Datasets after v0.5
type: research
project: wiki-langgraph
status: implemented
tags:
- evaluation
- langfuse
- knowledge-gap-review
- datasets
created: '2026-09-03'
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T13:36:31Z'
modified: '2026-09-04T13:36:31Z'
---
# Versioned Evaluation Datasets after v0.5

## Purpose

Refresh the repository evaluation corpus after the v0.5 knowledge-gap review release without
rewriting the original Langfuse baselines.

## Decisions

- Preserve `wiki-langgraph-research-v1` as an immutable comparison baseline.
- Add `wiki-langgraph-research-v2` for current research questions and resolved architecture facts.
- Evaluate knowledge-gap review separately from the bounded-agent dataset because it has a
  different contract: evidence-backed editorial findings, exact reviewed paths, partial-coverage
  disclosure, and filesystem immutability.
- Keep fixture execution isolated in temporary raw/wiki workspaces.
- Do not automatically publish or overwrite hosted Langfuse datasets from repository JSON.
- Keep research-v1 as the hosted default until the v2 expected outputs receive human review.
- Default knowledge-gap experiments to local fixture execution until that draft is reviewed and
  published; allow exact hosted dataset selection by timestamp afterward.

## Implementation

- Added six research-v2 cases covering evaluation maintenance, corpus design, architecture,
  reproducibility, experiment interpretation, and knowledge-gap safety.
- Added six knowledge-gap fixtures covering missing overview/links, possible duplication, missing
  compiled coverage, bounded partial review, a missing concept, and a possible conflict.
- Added deterministic category precision, recall, and F1 plus exact review scope, partial-review
  disclosure, read-only behavior, and finding bounds.
- Added exact hosted dataset-version selection and made `gap-eval` local by default.
- Added explicit exporter flushing, a stable telemetry service name, and `RETRIEVER` observations
  for query/research lexical lookup.

## Evidence and verification

- Dataset JSON is parsed during the evaluation test suite.
- Fixture selection is executed through the real deterministic pre-analysis before model review.
- The full repository suite passed with Langfuse tracing disabled and the documented request
  timeout isolated from the developer `.env`.

### Live Langfuse audit — 2026-09-04

- Confirmed the self-hosted Langfuse health endpoint at `http://localhost:3300` and exported fresh
  traces with SDK `4.15.1`, service name `wiki-langgraph`, environment `development`, and release
  `wiki-langgraph-local`.
- The configured `deepseek-v4-flash` model rejected all six knowledge-gap calls with an OpenCode
  region-opt-in error; those traces correctly recorded generation and experiment-item errors.
- A one-item `hy3` run emitted model/token/cache/reasoning usage but failed to return the required
  structured response.
- A one-item `glm-5.3-flash` possible-conflict run succeeded. It found one conflict, preserved the
  exact two-note review scope, performed no writes, and received `1.0` on all seven deterministic
  scores. Trace ID: `2fa009cbd9c6c2cb697de9ad0d3cfffe`.
- A fresh query trace confirmed `wiki.query` with sibling `wiki.retrieve` (`RETRIEVER`) and
  `ChatOpenAI` (`GENERATION`) children. Retrieval recorded three selected source paths; the
  generation recorded model, parameters, and 2,372 total tokens. Trace ID:
  `71df408e06948005bff87e6e7977992a`.
- A full six-case `glm-5.3-flash` baseline was stopped after two structured-response failures and
  one model call exceeded four minutes. The result is not a valid dataset baseline.
- Remaining observability gaps: DeepAgent filesystem calls are not represented as `TOOL`
  observations, and generation cost remains zero because the custom model has no matching pricing
  configuration.

## Open questions

- Category precision, recall, and F1 need calibration after collecting reviewed model outputs.
- The v2 and knowledge-gap datasets still need deliberate publication to Langfuse before hosted
  runs can use their names.
- CI blocking thresholds should wait until multiple clean experiment runs have been audited.
- Select and pin a model/provider combination that reliably supports DeepAgent tool calling and
  structured output before treating the six-case knowledge-gap experiment as a baseline.

## Related notes

- [Research/Langfuse Evaluation Baseline and Trace Findings](Langfuse%20Evaluation%20Baseline%20and%20Trace%20Findings.md)
- [Research/Agent Evaluation Fixtures and Findings](Agent%20Evaluation%20Fixtures%20and%20Findings.md)
- [Research/Bounded Agentic Workflow Architecture](Bounded%20Agentic%20Workflow%20Architecture.md)
- [Research/Wiki Pipeline and OKF Evolution](Wiki%20Pipeline%20and%20OKF%20Evolution.md)