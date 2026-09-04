## [Unreleased]

### Changed

- Kept the reviewed research-v1 dataset as the hosted default and marked new research and
  knowledge-gap datasets as local drafts pending human review.
- Expanded knowledge-gap evaluation to six failure modes and added category precision, recall,
  F1, exact review-scope, safety, and bound scores; running these cases requires a model/provider
  with reliable tool-calling and structured-output support.
- Added hosted dataset version selection, explicit Langfuse flushing, retrieval observations, a
  stable telemetry service name, and Langfuse 4.15.1.

## 2026-09-04

- Made research theme scoring explain unmatched expectations, normalized common word forms to
  reduce false negatives, and tightened research briefs around approval boundaries and post-run
  failure inspection. Grounding scores now explain missing retrieval or citations, and research
  key findings explicitly require source wikilinks.
- Clarified bounded knowledge-gap review prompts so scope-limited or inaccessible linked notes are
  treated as insufficient evidence rather than missing raw/wiki counterparts.

## 2026-09-03

- Added a post-v0.5 research dataset while preserving the original baseline, plus an executable
  knowledge-gap evaluation dataset with isolated fixtures and deterministic safety scores.

## 2026-08-31

- Added bounded, evidence-backed `review gaps` analysis that reuses the existing read-only
  DeepAgent factory and returns validated structured findings with an auditable file allowlist.

## 2026-08-01

- Added weekly Dependabot version updates for the project's `uv` dependencies.

## 2026-07-30

- Added optional Langfuse v4 tracing for pipeline steps and all current LLM paths.
- Reorganized the README around quick start, command workflows, optional AI features, linting, and configuration so first-time setup is easier to follow.
- Established a repository convention for recording meaningful application work as structured, linked notes under `data/raw/Research/`.

## 2026-07-28

### 0.4.0

- Added bounded LangGraph inspect/plan/act/verify/replan execution with `agent` CLI controls.
- Added opt-in, path-scoped read-only DeepAgent review for queued candidates.
- Updated OKF linting for code examples and numeric-dot note names; documented lowercase `index.md` behavior.
## 2026-07-30

- Added the first versioned research evaluation dataset with five structured session-note cases and expected themes/gaps for Langfuse experiments.
- Added a bounded-agent evaluation dataset with isolated clean, warning-review, and safe-stop fixtures.
