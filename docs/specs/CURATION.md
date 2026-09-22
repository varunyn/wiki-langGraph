# Curation specification

Status: accepted design; implementation pending

Governing decision: [ADR-0001](../decisions/0001-adopt-one-command-historical-curation.md)

## Product contract

`wiki-langgraph curate` is the primary weekly workflow for converting an arbitrary
raw Markdown corpus into an evidence-backed topic wiki and an immediately readable
digest.

The command has no required flags. It:

1. inventories the complete raw corpus without modifying it;
2. chooses an incremental or full-reconciliation plan;
3. extracts topic evidence from selected notes;
4. compares new evidence against the complete historical topic registry;
5. applies strongly supported changes to generated topic pages;
6. reports uncertain and contradictory findings for review;
7. runs the existing deterministic compile and optional index refresh;
8. writes a dated digest; and
9. prints a concise digest to the terminal.

The central invariant is **incremental computation with global memory**. Incremental
mode limits expensive extraction to changed notes. It does not limit retrieval to
changed notes.

## Terms

| Term | Definition |
| --- | --- |
| Raw note | Any eligible Markdown file below `Settings.raw_dir()`. Folder names carry no semantic meaning. |
| Evidence | A source-relative path, line range, excerpt, and normalized claim supporting a topic mention. |
| Topic mention | A structured assertion that a raw note discusses one candidate topic. |
| Topic | A canonical concept with aliases and evidence from raw notes. |
| Durable topic | A topic supported by accepted evidence from at least two distinct raw notes. |
| Emerging idea | A topic supported by only one distinct raw note; digest-only. |
| Relationship | A judgment connecting new evidence to a historical topic. |
| Incremental run | Extract changed notes, retrieve globally, and update affected topics. |
| Full reconciliation | Re-extract or reconsider the complete eligible corpus and rebuild derived registry state. |

## User-visible filesystem contract

All curation output is written below the configured generated wiki directory:

```text
<wiki>/
  Curation/
    Topics/
      <deterministic-slug>.md
    Digests/
      YYYY-MM-DD.md
```

`Curation/` is a reserved namespace in the generated wiki, not a required raw-folder
convention. Preflight fails without writing if a raw note would compile beneath that
namespace. Topic slugs are produced by code from the canonical topic name. Model
output never supplies a path. A same-day rerun replaces the managed contents of that
day's digest rather than creating a numbered duplicate.

Raw files are read-only inputs. The command must compare raw-file hashes captured at
the start and end of a run; a curation run must never cause a raw hash to change.
If a note changes externally while curation is running, discard that note's new
extraction, leave its previous registry entry unchanged, report it as deferred, and
process it on the next run.

## Run planning

### Full reconciliation

A full reconciliation is selected when any condition is true:

* no valid curation registry exists;
* the curation schema version changed;
* the extraction prompt or material curation configuration fingerprint changed;
* four successful incremental runs have completed since the last reconciliation;
* stored registry data fails validation.

### Incremental run

Otherwise, extraction is limited to Markdown notes whose SHA-256 differs from the
last successful curation state. Removed notes are also part of the delta so their
evidence can be pruned.

An incremental run with no changed or removed notes still writes or refreshes the
same-day digest with a `No source changes` result, performs no LLM call, and exits
successfully after non-strict lint.

The fingerprint covers the curation schema version, extraction and judgment prompt
versions, configured model identifier, candidate limit, auto-apply threshold, and
promotion threshold. Changing the reconciliation cadence alone does not invalidate
cached extractions.

## Processing stages

The terminal prints one progress line when each stage starts and one final summary.
Full reconciliation must also print processed/total counts during extraction.

### 1. Inventory

Enumerate eligible raw Markdown using the same recursive and generated-wiki exclusion
rules as `node_ingest`. Record source-relative POSIX paths and content hashes. Do not
infer note kind from directory names.

### 2. Prune stale evidence

Before counting support, remove evidence derived from deleted notes or from obsolete
hashes of changed notes. Mark every affected topic for reevaluation.

### 3. Extract topic mentions

For each selected note, ask the configured OpenAI-compatible chat model for JSON
matching this logical schema:

```text
TopicMention
  label: non-empty string
  aliases: list[string]
  claim: non-empty string
  evidence_excerpt: non-empty exact source excerpt
  line_start: positive integer
  line_end: integer >= line_start
```

Code validates that the excerpt occurs in the source text and derives the final line
range from the source. Invalid mentions are discarded and counted in the digest.
Prompts must request concepts that are reusable across notes, not generic section
headings or one-off administrative details.

Extraction results are cached by raw content hash and extraction fingerprint.

### 4. Generate historical candidates

For every extracted mention, build the union of at most 12 candidates from:

1. exact canonical-name or alias match;
2. the existing lexical scorer over topic names, aliases, summaries, and evidence;
3. authored-link neighbors for the source note;
4. optional QMD results when the QMD semantic backend is configured and available.

Exact matches are never displaced by lower-priority candidates. Candidate generation
is deterministic for identical registry and retrieval results. QMD failure degrades
to local retrieval and is reported as a warning.

Full reconciliation additionally compares topic clusters across the complete set of
cached mentions so topics that incremental retrieval kept separate can be merged or
flagged.

### 5. Judge relationships

For each mention/candidate pair, request one bounded structured judgment:

```text
RelationshipJudgment
  relation: supports | extends | contradicts | reframes | unrelated
  confidence: number from 0.0 through 1.0
  rationale: concise string grounded in supplied evidence
  evidence_ids: non-empty list of supplied evidence identifiers
```

The model receives only the new mention, candidate topic summary, aliases, and cited
evidence. It cannot see or choose filesystem paths and cannot apply a change.

Policy is owned by code:

* `supports` or `extends` at confidence `>= 0.80` may auto-apply.
* `reframes` is digest-only under `Needs review` in version one.
* `contradicts` is always digest-only under `Needs review`, regardless of confidence.
* Any non-`unrelated` judgment below `0.80` is digest-only under `Needs review`.
* `unrelated` creates a new candidate topic mention rather than mutating the
  historical candidate.

Confidence is a routing signal, not proof. Every applied relationship must retain
the evidence identifiers used to make it.

### 6. Normalize and promote topics

Deterministic normalization trims labels, collapses whitespace, performs casefolded
alias comparison, and selects a stable canonical record identifier. The model may
suggest aliases but cannot merge records without an accepted relationship judgment.

A topic becomes durable only when accepted evidence references at least two distinct
raw paths. Multiple mentions in one note count once toward promotion.

One-source topics appear under `Emerging ideas` in the digest and do not create a
topic page. A previously durable topic that falls below two current sources is not
deleted; it appears under `Needs review` with the reason `insufficient current
support`, and its page remains unchanged.

### 7. Run deterministic raw compilation

Run the existing deterministic raw-to-wiki compile before rendering curated
artifacts. This preserves existing raw compilation, authored-link provenance, and
frontmatter behavior. The curation graph must invoke the underlying application
service directly rather than recursively invoking the CLI.

### 8. Render affected topic pages

Durable topics are written to
`Curation/Topics/<deterministic-slug>.md`. Each page contains:

* managed frontmatter with a stable topic ID, canonical title, aliases, first-seen,
  last-seen, evidence count, distinct-source count, and curation provenance;
* a model-authored synthesis restricted to accepted evidence;
* an `Evidence` section linking to every contributing raw note or its compiled wiki
  counterpart;
* managed relationship sections that remain distinct from authored backlinks and
  ordinary semantic suggestions.

Reruns replace managed sections and preserve any content outside those markers.
Generated synthesis must cite evidence IDs; citations are resolved to links by code.

### 9. Render the dated digest

Write `Curation/Digests/YYYY-MM-DD.md` with these sections:

```text
# Curation Digest — YYYY-MM-DD
## Summary
## Recurring themes
## Connections to earlier work
## Created
## Enriched
## Emerging ideas
## Needs review
## Health
```

Empty sections may say `None`. The digest records run mode, source counts, model call
counts, invalid extraction counts, warnings, elapsed time, and links to affected
topic pages and evidence notes.

The terminal prints the summary, recurring themes, connections, created/enriched
counts, review count, warning count, and digest path. It must not dump model prompts,
raw JSON, or the full lint report unless verbose diagnostics are explicitly added in
a later version.

The first render uses `Health: pending` because final validation has not run yet.

### 10. Rebuild the index, refresh optional search, and lint

After topic pages and the provisional digest are staged successfully, regenerate
`index.md` from both raw-backed compiled notes and managed curation pages, then run
the existing optional QMD refresh and lint. Lint must recognize `Curation/` as
managed generated output: it validates managed frontmatter and index membership but
does not require a corresponding raw path and does not report orphan warnings for
digest pages. `curate` uses non-strict lint semantics: errors fail the command, while
warnings do not.

Rewrite the digest once with final health, warning, model-call, and elapsed-time
counts. Because its path and index metadata are unchanged, this final body update
does not require another index regeneration. If validation fails, rewrite the digest
with an `Incomplete run` status and do not claim that curation state was committed.
The terminal summary is printed only after this final digest render.

The root index includes durable topic pages in its concept registry and a separate
`Curation history` list of dated digests. Digest body text is not used to derive
index metadata, so finalizing health details cannot create index drift.

### 11. Commit state

Only after topic pages, the digest, deterministic compile, and lint complete without
an error does the command atomically save curation state. A failed run leaves the
previous successful registry and run counters intact. Generated files written before
failure must be safe to overwrite on retry.

## Manifest contract

Extend the existing manifest without removing `hashes` or `semantic_edges`:

```json
{
  "version": 2,
  "hashes": {},
  "semantic_edges": {},
  "curation": {
    "schema_version": 1,
    "last_success_at": "RFC3339 timestamp",
    "last_mode": "incremental | reconcile",
    "incremental_runs_since_reconcile": 0,
    "fingerprint": "sha256",
    "notes": {
      "relative/path.md": {
        "sha256": "...",
        "extraction_fingerprint": "...",
        "mentions": []
      }
    },
    "topics": {
      "stable-topic-id": {
        "canonical_name": "...",
        "aliases": [],
        "summary": "...",
        "first_seen": "RFC3339 timestamp",
        "last_seen": "RFC3339 timestamp",
        "evidence": []
      }
    }
  }
}
```

Loading remains soft-failure compatible: a missing or invalid curation section
triggers reconciliation rather than preventing ordinary `run` behavior. Saving from
any command must preserve recognized sections owned by other workflows.

## Failure behavior

| Failure | Required behavior |
| --- | --- |
| LLM unavailable before extraction | Exit nonzero; do not advance curation state. |
| One note fails extraction | Continue, report the note under `Needs review`, do not refresh that note's curation hash, and complete with warnings. |
| Invalid structured model output | Retry once with a validation error; then treat as a note extraction failure. |
| QMD unavailable | Fall back to local retrieval and emit a warning. |
| Topic render fails | Exit nonzero; do not advance curation state. |
| Lint warnings | Complete successfully and report them. |
| Lint errors | Exit nonzero; do not advance curation state. |
| Manifest write fails | Exit nonzero; preserve the previous manifest via atomic replacement. |

Partial extraction failures may still produce a digest, but that digest must state
that the run completed with warnings and must not claim those notes were curated.
Successful note and topic state may be committed; failed notes remain pending for the
next run. A completed-with-warnings run exits zero so isolated failures do not turn
the weekly workflow into an operational repair task.

## Idempotency and deletion

* Identical inputs, registry state, model responses, and date produce identical
  managed topic and digest contents apart from measured elapsed time.
* Evidence is keyed by source path, source hash, and normalized location so reruns
  cannot duplicate it.
* Removed notes have their evidence pruned during the next run.
* Curation never deletes a topic page automatically. Unsupported pages are surfaced
  for later explicit retirement policy.

## Configuration

Version one adds three advanced environment settings with defaults that require no
user action:

| Variable | Default | Meaning |
| --- | --- | --- |
| `WIKI_CURATE_FULL_RECONCILE_EVERY` | `4` | Successful incremental runs between reconciliations. |
| `WIKI_CURATE_CANDIDATE_LIMIT` | `12` | Maximum historical candidates judged per mention. |
| `WIKI_CURATE_AUTO_APPLY_THRESHOLD` | `0.80` | Minimum confidence for eligible relationships. |

The promotion threshold remains fixed at two distinct sources in version one.

## Evaluation and observability

The implementation must expose provider-neutral structured stage events through the
existing logger. Optional Langfuse integration may translate those events into
traces later; Langfuse is not required for the command to work.

The minimum evaluation corpus must contain:

* a topic repeated with different wording across old and new notes;
* two similar but distinct topics that must not merge;
* support and extension relationships;
* a contradiction and a reframe that must not auto-apply;
* a singleton emerging idea;
* a deleted source that drops a topic below the promotion threshold;
* an unchanged rerun; and
* a relationship discoverable only during full reconciliation.

Measure candidate recall separately from relationship accuracy. A correct judge
cannot recover a historical topic omitted by retrieval. Record model identifier,
prompt fingerprint, corpus fixture version, applied decisions, review decisions,
latency, and model-call counts for each evaluation run.

## Acceptance criteria

The verification checklist in ADR-0001 is normative. In addition, an implementation
is not complete until README examples describe only shipped flags and behavior,
`docs/ARCHITECTURE.md` shows the curation graph separately from the existing run
graph, and `uv run pytest` passes.
