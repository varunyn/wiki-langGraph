# Evaluation datasets

The repository keeps dataset definitions and isolated fixtures under `evals/` so changes are
reviewable and reproducible.

- `research_dataset.json` is the immutable `wiki-langgraph-research-v1` baseline.
- `research_dataset_v2.json` is a draft successor with post-v0.5 architecture,
  experiment-analysis, and knowledge-gap safety cases. Its expected outputs require human review.
- `agent_dataset.json` covers the bounded inspect → plan → act → verify → replan loop.
- `knowledge_gap_dataset.json` is a draft covering the read-only `review gaps` workflow. Review its
  expected outputs before publishing it to Langfuse.

Each item contains:

- `input.question` — the research question sent to the application.
- `input.source_notes` — notes expected to provide evidence.
- `expectedOutput.themes` — claims a strong answer should cover.
- `expectedOutput.gaps` — limitations a strong answer should acknowledge.
- `metadata` — category and source session IDs for reproducibility.

Run the hosted Langfuse dataset experiment with:

```bash
uv run wiki-langgraph eval
```

The command runs the hosted items through `wiki.research`, creates a linked dataset run, sends traces and deterministic scores to Langfuse, and prints the experiment result. It is intentionally single-concurrency for the first baseline.

The default fetches the reviewed `wiki-langgraph-research-v1` hosted baseline. Exercise the v2
draft locally while its expected outputs are under review:

```bash
uv run wiki-langgraph eval --dataset evals/research_dataset_v2.json --local
```

For exact hosted reproduction, select a dataset version with a timezone-aware timestamp, for
example `--dataset-version 2026-09-03T12:30:00Z`.

Bounded agent evaluations use isolated fixtures:

```bash
uv run wiki-langgraph agent-eval
```

They exercise the real inspect → plan → LangGraph → verify → replan path and score plan correctness, verification, safe stopping, and iteration bounds.

Knowledge-gap evaluations use temporary raw/wiki fixture copies and verify category precision,
recall and F1, exact reviewed scope, partial-review disclosure, finding bounds, and that no fixture
content was modified. They require a configured model/provider that reliably supports tool calls
and structured output, and default to the local draft:

```bash
uv run wiki-langgraph gap-eval
uv run wiki-langgraph gap-eval --hosted
```

Hosted runs require datasets with matching names to exist in Langfuse. Updating these JSON files
does not mutate hosted datasets; human-review expected outputs, then publish/version the items
deliberately before using hosted mode.
