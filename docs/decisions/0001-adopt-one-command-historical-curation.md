---
status: accepted
date: 2026-09-22
decision-makers: Varun Yadav
---

# Adopt one-command historical curation

## Context and Problem Statement

wiki-langgraph currently exposes its implementation stages through separate
commands and settings: ingest, compile, index, lint, query, research, and review.
That model works for active pipeline development, but it asks a person who checks
their wiki roughly weekly to remember how to operate and interpret the pipeline.
The command can finish useful compilation work while still appearing to fail on
non-blocking lint warnings, and it does not produce a cross-note synthesis as its
primary result.

The desired product behavior is one command that turns an arbitrary raw Markdown
corpus into immediately useful, evidence-backed synthesis and a durable wiki. New
or changed notes should trigger computation, but correlations must be evaluated
against historical material. Raw files are source material and must never be
modified by curation.

The detailed behavioral contract is defined in
[the curation specification](../specs/CURATION.md).

## Decision Drivers

* Normal use should require one command and no knowledge of graph stages.
* Every successful run should provide value without requiring the user to browse
  the generated wiki.
* A new note must be able to reinforce, extend, contradict, or reframe an idea from
  any earlier note.
* Routine runs over approximately 100 notes should target completion within five
  minutes on the configured model; full reconciliation may take longer but must
  report progress.
* Raw Markdown must remain the immutable source of truth for curation.
* Durable topic pages must have evidence from at least two distinct raw notes.
* Ambiguous AI judgments must remain visible without blocking unrelated work.
* Version one must reuse the existing Python, LangGraph, manifest,
  OpenAI-compatible model, and optional QMD integration. It must not require a
  database, queue, watcher, web UI, or additional service.

## Considered Options

* Reprocess the full corpus through the model on every run.
* Process only new or changed notes.
* Trigger from changed notes, retrieve globally, and periodically reconcile the
  complete corpus.

## Decision Outcome

Chosen option: **Trigger from changed notes, retrieve globally, and periodically
reconcile the complete corpus.**

The public workflow is `wiki-langgraph curate`. A normal run extracts structured
topic evidence only from new or changed raw notes, retrieves candidate matches from
the complete historical topic registry and wiki, judges the bounded candidates,
and updates only affected generated artifacts. The first run, material curation
configuration changes, and every fourth successful incremental run trigger a full
reconciliation automatically. The user does not need a separate deep-mode command.

Every successful run writes a dated generated digest and prints a concise version
to the terminal. Relationships that clear the auto-apply policy may update generated
topic pages. Uncertain or contradictory findings are reported in the digest under
`Needs review` and do not block the run. Lint errors remain failures; lint warnings
are reported but are non-blocking for `curate`.

### Consequences

* Good, because the weekly workflow becomes one outcome-oriented command.
* Good, because incremental cost is bounded without isolating new material from
  historical context.
* Good, because evidence and relationship judgments are reusable state rather than
  prose that must be regenerated every run.
* Good, because raw notes remain untouched and generated changes remain auditable.
* Bad, because the manifest becomes a versioned curation data store and requires
  explicit migration, validation, and pruning behavior.
* Bad, because candidate retrieval can miss a distant semantic relationship between
  reconciliations; the scheduled full reconciliation mitigates but cannot eliminate
  this risk.
* Bad, because model confidence is not truth. Auto-apply thresholds must be tested
  against representative fixtures, and evidence provenance must remain visible.
* Neutral, because existing `run`, `agent`, `lint`, and review commands remain as
  diagnostic and compatibility surfaces rather than the primary user journey.

## Non-goals

* Continuous synchronization or filesystem watching.
* Editing, moving, renaming, or deleting raw notes.
* Inferring semantics from raw folder names.
* A web UI, Obsidian plugin, database server, message queue, or multi-user platform.
* Replacing the existing deterministic compiler, query flow, or provenance rules.
* Making TypeSafe or Langfuse a required dependency. Structured judgments and
  observability hooks must remain provider-neutral in version one.

## Implementation Plan

* **Affected paths**:
  * Add `src/wiki_langgraph/curation_models.py` for typed evidence, topic,
    relationship, run-plan, and run-result records.
  * Add `src/wiki_langgraph/curation_extract.py` for structured per-note extraction.
  * Add `src/wiki_langgraph/curation_retrieve.py` for global candidate generation
    using the registry, existing lexical scoring, authored links, and optional QMD.
  * Add `src/wiki_langgraph/curation_judge.py` for bounded relationship judgments.
  * Add `src/wiki_langgraph/curation_render.py` for topic pages, dated digests, and
    terminal summaries.
  * Add `src/wiki_langgraph/curation.py` as the application service that plans and
    executes one idempotent curation transaction.
  * Extend `src/wiki_langgraph/manifest.py` with a validated `curation` section while
    preserving `hashes` and `semantic_edges`.
  * Extend `src/wiki_langgraph/linking.py` so the generated index includes the
    reserved curation namespace after curated artifacts are rendered.
  * Extend `src/wiki_langgraph/lint.py` so managed curation pages are validated as
    generated output and are not mistaken for raw-backed concepts.
  * Extend `src/wiki_langgraph/state.py`, `src/wiki_langgraph/nodes.py`, and
    `src/wiki_langgraph/graph.py` with curation-specific state and graph nodes; do
    not change the topology used by the existing `run` command.
  * Add the `curate` subcommand to `src/wiki_langgraph/cli.py`.
  * Add curation defaults and validation to `src/wiki_langgraph/config.py` and
    `.env.example`.
  * Add focused tests under `tests/test_curation_*.py`, plus CLI and manifest
    coverage in `tests/test_cli_run.py` and `tests/test_manifest.py`.
  * After implementation, update `README.md`, `docs/ARCHITECTURE.md`, and
    `CHANGELOG.md` to describe shipped behavior.
* **Dependencies**: add no required runtime dependency. QMD remains optional.
* **Patterns to follow**:
  * Use `Settings` for environment-backed configuration.
  * Use typed dataclasses or `TypedDict` records rather than passing unvalidated
    model prose between stages.
  * Reuse atomic manifest writes from `manifest.save_manifest`.
  * Reuse the configured `ChatOpenAI` boundary and `_message_text` normalization.
  * Preserve explicit authored-link provenance separately from semantic or curated
    relationships.
  * Use managed Markdown markers for generated sections so reruns replace rather
    than duplicate content.
* **Patterns to avoid**:
  * Do not send the complete raw corpus in one prompt.
  * Do not use folder names as lifecycle or topic labels.
  * Do not allow model output to choose filesystem paths directly.
  * Do not write curated artifacts outside the reserved generated-wiki namespace
    `Curation/`; fail preflight if a raw note would compile to that namespace.
  * Do not update the manifest until all generated files for the run have been
    written successfully.
  * Do not delete a topic page automatically when its current support falls below
    the promotion threshold; flag it for review.
  * Do not merge curated relationships into authored backlinks.
* **Configuration**:
  * `WIKI_CURATE_FULL_RECONCILE_EVERY`, default `4` successful incremental runs.
  * `WIKI_CURATE_CANDIDATE_LIMIT`, default `12` historical candidates per extracted
    topic.
  * `WIKI_CURATE_AUTO_APPLY_THRESHOLD`, default `0.80`.
  * The distinct-source promotion threshold is fixed at `2` for version one.
* **Migration steps**:
  1. Missing curation state is treated as an uninitialized registry and triggers a
     full reconciliation.
  2. Preserve existing manifest hashes and semantic cache entries when saving the
     new curation section.
  3. Ship `curate` alongside existing commands; do not redirect or remove `run`.
  4. Only after curation verification passes should documentation present `curate`
     as the recommended weekly workflow.

## Verification

- [ ] `uv run pytest` passes without adding a required external service.
- [ ] `wiki-langgraph curate` leaves every raw-file byte unchanged.
- [ ] A fixture with one mention does not create
  `Curation/Topics/<slug>.md` and does appear
  under `Emerging ideas` in the digest.
- [ ] A fixture with supporting evidence in two distinct notes creates one topic
  page with provenance links to both notes.
- [ ] A new note can update a topic whose earlier evidence was processed in a prior
  run without re-extracting unchanged raw notes.
- [ ] Relationship fixtures cover `supports`, `extends`, `contradicts`, `reframes`,
  and `unrelated`.
- [ ] Uncertain and contradictory findings appear under `Needs review` and do not
  modify the affected topic page.
- [ ] Repeating `curate` with no source changes does not duplicate pages, evidence,
  managed sections, or digest entries.
- [ ] The first run and every fourth successful incremental run select full
  reconciliation automatically; a changed curation configuration also forces it.
- [ ] Deleted or changed sources have stale evidence pruned before promotion counts
  are evaluated.
- [ ] A topic that falls below two supporting sources is preserved and flagged for
  review rather than deleted.
- [ ] Lint warnings are reported but do not make `curate` exit nonzero; lint errors do.
- [ ] Progress identifies the current stage during full reconciliation.
- [ ] A representative 100-note incremental fixture completes within five minutes
  against the configured integration-test model, with model and hardware recorded
  alongside the measurement.

## Pros and Cons of the Options

### Reprocess the full corpus on every run

* Good, because every relationship can be reconsidered on every run.
* Good, because persistent extracted-topic state is less important.
* Bad, because latency and model usage grow with the entire corpus.
* Bad, because weekly use becomes increasingly slow as knowledge compounds.

### Process only new or changed notes

* Good, because routine runs are fast and inexpensive.
* Good, because the existing hash manifest already identifies changed notes.
* Bad, because historical relationships can be missed or evaluated without enough
  evidence.
* Bad, because topic clusters can drift without ever being globally reconsidered.

### Trigger from changes, retrieve globally, and reconcile periodically

* Good, because routine extraction cost scales with the delta.
* Good, because every new topic is compared with bounded candidates from historical
  memory.
* Good, because periodic reconciliation corrects accumulated retrieval and
  normalization errors.
* Bad, because it introduces versioned topic-registry state and more failure modes.
* Bad, because correctness depends on both candidate recall and relationship
  judgment quality.

## More Information

Design references considered during discovery:

* [atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler)
  for lifecycle, provenance, freshness, review, and incremental repair patterns.
* [Tencent/WeKnora](https://github.com/Tencent/WeKnora) for asynchronous knowledge
  processing, progress reporting, and end-user knowledge synthesis patterns.

Revisit this decision if routine incremental runs exceed the five-minute target,
candidate-retrieval recall proves inadequate on representative fixtures, or the
manifest becomes too large or contentious for safe atomic JSON updates.
