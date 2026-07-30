# Research evaluation dataset

`research_dataset.json` is the first versioned local corpus for evaluating the `wiki.research` task.

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

The command fetches `wiki-langgraph-research-v1` from Langfuse and creates a dataset run. Use `--local` only when testing the JSON fixture without relying on the hosted dataset.

Bounded agent evaluations use isolated fixtures:

```bash
uv run wiki-langgraph agent-eval
```

They exercise the real inspect → plan → LangGraph → verify → replan path and score plan correctness, verification, safe stopping, and iteration bounds.
