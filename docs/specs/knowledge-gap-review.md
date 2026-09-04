# Knowledge-gap review with the existing DeepAgent

## Problem Statement

As a wiki author, I can compile, link, and lint my Markdown vault, but I do not have a focused way
to understand what knowledge is missing or poorly connected across a topic. Existing lint findings
identify mechanical health problems such as broken links and orphan notes, but they do not answer
editorial questions: which frequently mentioned concept lacks a defining note, which notes duplicate
each other, where the raw corpus contains detail absent from the compiled wiki, or which topic needs
an overview note. I need an optional review that produces actionable, evidence-based suggestions
without silently changing my vault.

## Solution

Add `wiki-langgraph review gaps [scope]`, an explicit, read-only editorial review command. The
command will resolve a bounded set of raw and compiled notes, collect deterministic graph and lint
metadata, and invoke the repository's existing DeepAgent through `create_wiki_deep_agent`. The
DeepAgent will use its allowlisted filesystem tools to inspect evidence, compare notes, and return a
validated structured result. The application will render that result as Markdown for a human.

The report will prioritize gaps, duplicate or conflicting concepts, weakly connected notes, missing
overview notes, and source-to-wiki coverage concerns. Every finding will identify the evidence that
the agent actually inspected, explain why the finding matters, and recommend a next action. The
first release is advisory only. It will not create, edit, approve, reject, or compile notes. A later,
separate feature may turn selected findings into candidate drafts.

## User Stories

1. As a wiki author, I want to review a topic folder for knowledge gaps, so that I can improve one
   area of my vault without scanning every note manually.
2. As a wiki author, I want to review the whole corpus when no scope is specified, so that I can
   identify cross-topic gaps and editorial priorities.
3. As a wiki author, I want each finding to name the affected note or concept, so that I can move
   directly from the report to the evidence.
4. As a wiki author, I want the report to distinguish missing concepts from weak linking, so that I
   can choose whether to write a note or improve navigation.
5. As a wiki author, I want repeated references to an undefined concept identified, so that I can
   create a canonical concept note when it is warranted.
6. As a wiki author, I want potential duplicate notes identified with their differing focus, so that
   I can consolidate or clearly separate overlapping knowledge.
7. As a wiki author, I want potential contradictions called out as review questions rather than
   automatically resolved, so that factual judgment remains mine.
8. As a wiki author, I want notes with weak links to their topic identified, so that useful material
   does not remain isolated from the rest of the wiki.
9. As a wiki author, I want a suggestion when a dense topic lacks an overview note, so that readers
   have an understandable entry point.
10. As a wiki author, I want source-to-wiki coverage concerns surfaced when raw notes appear to
    contain material absent from compiled notes, so that AI authoring does not quietly lose useful
    content.
11. As a wiki author, I want findings ranked by likely value and confidence, so that I can address
    the most useful editorial work first.
12. As a wiki author, I want the review to state when it has insufficient evidence, so that uncertain
    suggestions are not mistaken for authoritative conclusions.
13. As a wiki author, I want the review command to be read-only, so that running it cannot alter my
    raw notes, compiled wiki, manifest, review queue, or QMD index.
14. As a wiki author, I want a clear setup failure before agent invocation when no usable
    tool-calling chat endpoint is configured, so that the command explains what is missing and does
    not change the vault.
15. As a wiki author, I want the normal compile and lint paths to behave exactly as before, so that
    editorial analysis remains an explicit opt-in activity.
16. As a reviewer, I want a compact summary plus detailed findings, so that I can decide whether a
    topic needs work before reading the full report.
17. As a maintainer, I want the normalized scope, reviewed paths, omitted-note count, and read
    allowlist visible in the command output, so that the DeepAgent's access is auditable.
18. As a future feature author, I want report findings to have a validated data contract, so that a
    later draft-generation workflow can consume selected findings without parsing prose.

## Command and Scope Contract

- The command is `wiki-langgraph review gaps [scope] [--limit N]`.
- `scope` is optional. When provided, it is a POSIX-style path relative to both the configured raw
  and wiki roots. It may identify one Markdown file or a directory whose Markdown descendants are
  reviewed. Version 1 does not accept globs, note titles, fuzzy topic names, or absolute paths.
- Scope normalization rejects an empty explicit value, `..`, `~`, absolute paths, and any resolved
  path that escapes either configured root, including through a symlink.
- A scope is valid when it identifies a Markdown file or directory in at least one of the raw or
  wiki roots. Raw paths are mapped to their canonical wiki relative path with the existing
  `strip_redundant_wiki_prefix` rule; this preserves compilation behavior for raw paths under a
  redundant `Wiki/` prefix. Wiki files are also enumerated independently so raw-only and wiki-only
  notes remain visible as logical note records.
- Omitting `scope` selects the configured raw/wiki corpus. Generated or reserved `index.md` and
  `log.md` files are excluded from review candidates.
- `--limit` bounds logical note records, not individual raw/wiki files. It defaults to 24, must be at
  least 1, and is capped at 100.
- Candidate selection is deterministic. Records with relevant lint findings or a missing raw/wiki
  counterpart come first; remaining records are ordered by descending outgoing authored-link count
  and then by canonical POSIX wiki-relative path. Authored-link count is derived from explicit
  `[[wikilinks]]` only and does not include Markdown links or semantic suggestions.
- If eligible records exceed the limit, the result is partial. It must list the reviewed paths,
  report the omitted count, and recommend a narrower scope. It must not imply that the unreviewed
  records contain no gaps.
- An empty but valid directory scope succeeds without creating or invoking a DeepAgent and renders a
  `no reviewable notes` report. Invalid scopes, unreadable selected notes, missing agent setup,
  malformed agent output, and DeepAgent failures return a non-zero exit status with a specific
  diagnostic.

## Module and Interface Design

- Add a `knowledge_gap_review.py` orchestration module with one external interface equivalent to:

  ```python
  def review_knowledge_gaps(
      settings: Settings,
      *,
      scope: str | None = None,
      limit: int = 24,
  ) -> KnowledgeGapReviewResult: ...
  ```

  The module owns scope resolution, deterministic pre-analysis, permission construction, DeepAgent
  invocation, structured-result validation, and Markdown rendering. The CLI is a thin adapter over
  this interface.
- Reuse `deep_agent.create_wiki_deep_agent`; do not add a second DeepAgent factory, custom agent
  class, parallel control loop, or knowledge-gap-specific subagent. A new compiled DeepAgent runtime
  may be created for each command invocation, as it is for existing deep review, but agent creation
  remains centralized in the existing factory.
- Extend `create_wiki_deep_agent` only as needed to pass a structured `response_format` through to
  `deepagents.create_deep_agent`. Knowledge-gap code must not call the third-party factory directly.
- Keep the existing candidate-specific `deep_review.review_candidates` workflow separate. Shared
  mechanical helpers such as final-message extraction may move to a neutral module when genuinely
  reused, but candidate review and knowledge-gap review must retain distinct result types and
  prompts.
- Keep knowledge-gap review outside the normal LangGraph compile graph and outside the bounded
  `agent` loop. It is an explicit editorial action, not a compile node and not an automatic response
  to lint output.
- Broaden the parent `review` command help and documentation so it covers both queued compile
  candidate decisions and read-only editorial review. `review gaps` does not read or mutate the
  candidate queue.

## Deterministic Pre-analysis

Before invoking the DeepAgent, the orchestration module will build logical note records keyed by
canonical POSIX wiki-relative path. It will build link resolution and lint metadata against the full
raw corpus before filtering issues to the selected records; running lint against only the selected
files would falsely classify valid links to out-of-scope notes as unresolved. Pre-analysis will
include:

- raw and wiki file availability;
- note title or first heading when available;
- explicit authored-link outgoing and incoming relationships;
- unresolved-link and orphan lint findings relevant to the selected scope; and
- the reason each logical note was selected by the bounded policy.

This metadata focuses the review and makes the selected subset auditable, but it is not itself a
knowledge-gap conclusion. Lint is evidence, not the definition of a gap. The report must not repeat
an orphan or unresolved-link finding as a DeepAgent insight without additional inspected context.
Semantic suggestions must remain a separate provenance layer and must not be counted as authored
connections.

## Agentic Behavior and Read Authority

- The DeepAgent receives metadata and virtual paths, not the full selected corpus embedded in one
  prompt. It must use its filesystem tools to inspect note contents, compare evidence, and decide
  which allowed notes require deeper reading before it produces findings.
- The prompt must tell the DeepAgent to continue gathering evidence until it can support a finding
  or explicitly state that evidence is insufficient. Planning, repeated reads/searches, and the
  existing DeepAgent's internal task delegation are permitted but not required.
- Each finding must cite at least one allowlisted path that the agent inspected. Duplicate and
  conflict findings must cite at least two distinct compared paths. The orchestration module derives
  the inspected-path set from successful filesystem tool calls in the returned message trace; a
  path claimed only in model prose does not count as inspected. Paths outside either the inspected
  set or the selected allowlist are invalid evidence.
- The agent may read only the selected raw/wiki files, applicable `/skills/**`, and `/AGENTS.md` when
  present. It may not receive directory-wide access merely because one selected note is inside that
  directory.
- Because the existing virtual filesystem backend is rooted at `settings.project_root`, configured
  raw/wiki roots and selected files must resolve beneath that project root. The command fails clearly
  before agent creation when they do not; it must not construct misleading virtual allowlist paths.
- Invoke `create_wiki_deep_agent` with `read_only=True` and an explicit file-level `read_paths`
  allowlist. The existing ordered allow-then-deny-all filesystem permissions remain the enforcement
  mechanism and are inherited by the existing general-purpose subagent.
- No filesystem write is allowed. In-memory DeepAgent todo state is acceptable; raw/wiki files,
  manifest content, review candidates, QMD state, and project files must remain unchanged.
- The command output must print the normalized scope, partial/full status, reviewed logical paths,
  omitted count, and effective file-level read allowlist before or alongside the report.

## Structured Result and Markdown Report

The DeepAgent must return a validated structured response. The implementation may use Pydantic
models, dataclasses plus explicit validation, or equivalent concrete types, but the data contract is:

```text
KnowledgeGapReviewResult
  scope: str | null
  partial: bool
  reviewed_paths: list[str]
  omitted_count: int
  summary: str
  insufficient_evidence: list[str]
  findings: list[KnowledgeGapFinding]

KnowledgeGapFinding
  category: missing_concept | missing_overview | weak_connection |
            possible_duplicate | possible_conflict | source_coverage_gap
  priority: high | medium | low
  confidence: float from 0.0 through 1.0
  affected_paths: non-empty list[str]
  evidence: non-empty list[Evidence]
  why_it_matters: str
  recommendation: str
  uncertainty: str | null

Evidence
  path: str
  observation: str
```

The application, not the model, renders the validated result into deterministic Markdown. The
report starts with scope, coverage, and a compact summary, followed by findings ordered by priority,
descending confidence, category, and affected path. Invalid categories, out-of-range confidence,
empty evidence, evidence outside the allowlist, or an unparseable structured response fail the
command rather than being printed as if valid. Potential duplicates and conflicts must use cautious
language and retain uncertainty; they must not present an unverified conclusion as fact.

The orchestration module owns `scope`, `partial`, `reviewed_paths`, and `omitted_count`. Agent output
must not override those deterministic fields. The module merges validated agent findings with the
deterministic coverage fields before rendering the final `KnowledgeGapReviewResult`.

## Testing Decisions

- Treat `review_knowledge_gaps` as the primary module seam. Exercise scope resolution, selection,
  permission construction, agent invocation, validation, and result rendering through that
  interface. Add focused CLI adapter tests for argument validation, displayed audit information,
  output, and exit status.
- Reuse existing read-only DeepAgent review tests as prior art. Cover empty input without agent
  creation, selected-scope invocation with an exact file allowlist, and extraction of the structured
  result.
- Use temporary raw and wiki directories in every test to prevent a developer `.env` from pointing
  a review at a real vault.
- Include behavior tests for every finding category using deterministic fake DeepAgent responses.
  Assert that validation and Markdown rendering preserve category, affected paths, evidence,
  priority, confidence, recommendation, and uncertainty.
- Add a scripted tool-calling test in which the DeepAgent reads allowed notes before reporting a
  finding. Assert that the orchestration module derives the inspected paths from the tool trace and
  rejects a response that claims evidence from an allowed but unread note. This distinguishes the
  agentic inspect/compare/report path from a direct one-shot prompt.
- Test actual permission enforcement, not only permission object construction: selected files,
  skills, and optional `AGENTS.md` can be read; an unselected project file cannot be read; writes to
  selected and unselected paths are denied; and the inherited general-purpose subagent cannot bypass
  the same rules.
- Test that the feature does not alter raw files, wiki files, manifest content, candidate metadata,
  QMD state, or unrelated project files before and after successful and failed reviews.
- Test exact-file scope, directory scope, omitted corpus scope, raw-only and wiki-only records,
  symlink/path traversal rejection, deterministic ordering, custom limits, an empty valid scope, an
  over-limit partial result, unreadable selected notes, missing tool-calling model configuration,
  malformed structured output, and a DeepAgent failure.
- Test that evidence outside the allowlist, duplicate/conflict findings with fewer than two evidence
  paths, and findings without evidence are rejected.
- Keep prompt wording and helper call order as implementation details. Test observable behavior at
  the module interface instead.

## Out of Scope

- Automatic creation, rewriting, approval, rejection, or deletion of wiki notes.
- Automatic repair of lint findings.
- Adding the knowledge-gap review to normal `run`, `agent`, query, or research execution.
- Creating another DeepAgent factory, custom DeepAgent class, or knowledge-gap-specific subagent.
- Persisting LangGraph checkpoints for the compile graph or this read-only review.
- Introducing QMD as a requirement for knowledge-gap review.
- Accepting fuzzy topic selectors, note titles, or glob scopes in version 1.
- Replacing human editorial judgment with DeepAgent recommendations.
- Broad web research or retrieval outside the configured local wiki corpus.
- Persisting reports or adding a user interface beyond CLI Markdown output and documentation.

## Documentation and Acceptance

- Update `README.md`, `docs/ARCHITECTURE.md`, CLI help, and `CHANGELOG.md` when the feature is
  implemented. Documentation must continue to distinguish authored links, semantic suggestions,
  compile-candidate review, and knowledge-gap review.
- The feature is accepted when the command resolves and displays a deterministic bounded scope,
  the existing DeepAgent inspects only the allowlisted notes, validated evidence-backed findings are
  rendered deterministically, no persistent state changes, failures are specific and non-zero, and
  normal `run`, `agent`, lint, query, research, and candidate-review behavior remains unchanged.
- Draft generation may be proposed only after users find these reports accurate and useful. It must
  remain a separate, opt-in workflow with its own authority decisions.
- Because no issue tracker is configured for this project, this document is the local specification.
