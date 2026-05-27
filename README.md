# wiki-langgraph

LangGraph pipeline that **ingests** raw markdown, **compiles** an Obsidian-style vault (wikilinks, authored backlinks, semantic `See also`, `Index.md`), optionally runs **LLM authoring**, supports **query → save → future context** compounding, refreshes a local **[QMD](https://github.com/tobi/qmd)** index when enabled, and **lints** the vault.

## What it does now

- Compiles raw markdown into a generated Obsidian wiki.
- Preserves provenance with `compiled_from:` frontmatter.
- Keeps authored **Backlinks** separate from semantic **See also** / **Related (semantic)** suggestions.
- Generates a rich `Index.md` with note metadata and graph counts.
- Supports incremental LLM compile with optional enrichment of existing wiki notes.
- Adds a risk-based review queue for generated LLM candidates.
- Lets you ask questions over the compiled wiki with `query`.
- Lets you synthesize deeper research briefs with `research`.
- Lets you save useful answers under raw `Queries/`, then compile them into future query context.
- Optionally uses QMD for semantic related-note lookup and index/embed refresh.
- Lints unresolved wikilinks, orphan notes, stale output, and index drift.
- Excludes the configured generated wiki directory from ingest when it lives inside the raw vault.

## Background: the “LLM Wiki” pattern

Andrej Karpathy [posted on X](https://x.com/karpathy/status/2039805659525644595) about a workflow where the model does not only retrieve chunks at question time (classic RAG), but **incrementally builds and maintains a persistent, interlinked markdown wiki** between you and your raw sources—so structure and synthesis **compound** instead of being re-derived every query. He expanded the idea in a copy-paste **idea file** ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)).

**wiki-langgraph** is a **concrete implementation** of parts of that pattern: a reproducible compile pipeline, vault linking, optional LLM passes, optional local search/embeddings via QMD, and rule-based lint. The gist stays intentionally abstract; this repo pins directory layout, env vars, and graph behavior—see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full node graph and module map.

## Prerequisites

| Requirement                                             | When you need it                                                                                                                                                                        |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python 3.12+**                                        | Always                                                                                                                                                                                  |
| **[uv](https://docs.astral.sh/uv/)**                    | Always (install deps and run the CLI)                                                                                                                                                   |
| **OpenAI-compatible HTTP API** (`WIKI_OPENAI_API_BASE`) | `query`, `research`, `WIKI_LLM_COMPILE=true`, and/or `WIKI_SEMANTIC_LINKS=true` with `WIKI_SEMANTIC_BACKEND=llm` (e.g. [Ollama](https://ollama.com/) with OpenAI compatibility, llama.cpp server, vLLM, etc.) |
| **[QMD](https://github.com/tobi/qmd)** on `PATH`        | `WIKI_SEMANTIC_BACKEND=qmd` and/or `WIKI_QMD_REFRESH=true` (hybrid search + optional `qmd embed` after compile)                                                                         |
| **Obsidian**                                            | Optional; useful as the reader/UI for the generated vault, not required to run the pipeline                                                                                             |

**Minimal run:** no `.env` required if you are fine with defaults `data/raw` → `data/wiki` under the repo and you do not enable LLM compile, semantic LLM features, or QMD refresh. Anything that calls the chat API needs a reachable base URL and model id. QMD refresh is off by default for this minimal path.

## Setup

```bash
uv sync
cp .env.example .env   # optional; set paths and features below
```

Settings load from the environment with prefix **`WIKI_`** (and optional **`.env`** in the current working directory). **`cp .env.example .env`** is the usual starting point; adjust only what you use.

## Run

```bash
uv run wiki-langgraph run -v
uv run wiki-langgraph query "How should I debug RAG failures?"
uv run wiki-langgraph query "How should I debug RAG failures?" --save
uv run wiki-langgraph research "Compare RAG failures and evaluation loops" --save
uv run wiki-langgraph review list
uv run wiki-langgraph lint
uv run wiki-langgraph version
```

### Command reference

| Command | Purpose |
| --- | --- |
| `wiki-langgraph run -v` | Run ingest → compile → optional QMD refresh → lint. |
| `wiki-langgraph query "..."` | Answer a question using retrieved compiled wiki notes. |
| `wiki-langgraph query "..." --save` | Save the answer as a raw note under `Queries/` so future runs can compile it. |
| `wiki-langgraph research "..."` | Synthesize a structured research brief from broader retrieved wiki context. |
| `wiki-langgraph research "..." --save` | Save the brief as a raw note under `Research/` so future runs can compile it. |
| `wiki-langgraph review list/show/approve/reject` | Inspect and resolve queued LLM compile candidates. |
| `wiki-langgraph lint` | Check raw/wiki health without compiling. |
| `wiki-langgraph lint --fix --dry-run` | Preview unresolved wikilink cleanup. |
| `wiki-langgraph version` | Print package version. |

### Lint catches unresolved links, orphan notes, and stale wiki output

`wiki-langgraph lint` checks the raw/wiki pair for a few high-signal problems:

- unresolved `[[wikilinks]]` inside the ingested raw tree
- markdown notes with **no outgoing `[[wikilinks]]`** (`W_ORPHAN_NOTE`), which are often suspect when the source corpus is incomplete or incorrectly split
- raw notes newer than their compiled wiki output (`W_STALE_WIKI`)
- `Index.md` drift versus the compiled note catalog

Generated index notes are exempt from the orphan-note warning. To clean unresolved links automatically:

```bash
uv run wiki-langgraph lint --fix --dry-run   # preview: fuzzy rewrites + strip the rest
uv run wiki-langgraph lint --fix             # edit raw .md under WIKI_DATA_RAW_DIR
uv run wiki-langgraph lint --fix --fix-mode strip    # plain text only (no fuzzy rename)
uv run wiki-langgraph lint --fix --fix-mode rewrite  # fuzzy only; leave what is still broken
```

**`--fix`** updates **raw** sources: it tries a **single unambiguous fuzzy match** to a catalog note label (`difflib`, configurable `--fuzzy-cutoff`), then turns any remaining broken links into **plain text** (keeping `[[note|alias]]` as `alias`). Re-run **`wiki-langgraph run`** so the wiki matches. It does **not** invent files for links that point outside your corpus—those become plain text unless fuzzy finds a close in-vault name.

### Query and save explorations

Ask a question against the compiled wiki:

```bash
uv run wiki-langgraph query "How should I debug RAG failures?"
```

The query command uses a local lexical retriever over compiled wiki notes, sends the top notes to the configured chat model, and prints the answer plus source notes. Add `--save` to write the answer back into the raw vault under `Queries/`:

```bash
uv run wiki-langgraph query "How should I debug RAG failures?" --save
uv run wiki-langgraph run -v
```

The saved raw note includes the source question, generated answer, and wikilinks to retrieved source notes. The next compile run turns it into a normal wiki page so future queries can use it as context.

Saved query layout:

```text
raw vault:
  Queries/How should I debug RAG failures.md

compiled wiki:
  wiki/Queries/How should I debug RAG failures.md
```

The raw `Queries/` note is the source of truth. The compiled `wiki/Queries/` page is generated output and appears in `Index.md` like any other compiled note.

### Research briefs

Use `research` when you want a broader synthesis instead of a short answer:

```bash
uv run wiki-langgraph research "Compare RAG failures and evaluation loops"
uv run wiki-langgraph research "Compare RAG failures and evaluation loops" --save
uv run wiki-langgraph run -v
```

Research mode uses the same compiled-wiki retrieval path as `query`, but defaults to more source notes and asks the model for a structured brief with summary, findings, source notes, related concepts, open questions, and follow-ups. With `--save`, the raw note is written under `Research/` and compiles into `wiki/Research/` on the next run, so those investigations become future retrieval context too.

## Configuration (environment variables)

All names are listed in **`.env.example`**. Below is what matters and when to set it.

### Paths and project layout

| Variable             | Purpose                                                                                                                                                                                         |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WIKI_DATA_RAW_DIR`  | Root folder to **ingest** (recursive). Default: `<project>/data/raw`.                                                                                                                           |
| `WIKI_DATA_WIKI_DIR` | **Compiled vault** output. Default: `<project>/data/wiki`. Set this when your vault lives inside a larger Obsidian tree; see `.env.example` for avoiding duplicated `wiki/wiki/` path segments. |

If unset, paths are derived from the package location (repo root when developing). If `WIKI_DATA_WIKI_DIR` is inside `WIKI_DATA_RAW_DIR`, the generated wiki folder is excluded from ingest and lint source enumeration so generated pages do not feed back as raw input.

### OpenAI-compatible LLM (chat HTTP)

| Variable                       | Purpose                                                                                                                                       |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `WIKI_OPENAI_API_BASE`         | Base URL for chat completions, e.g. `http://127.0.0.1:11434/v1` (Ollama). **Required** for `query`, `research`, `WIKI_LLM_COMPILE`, or semantic LLM backend. |
| `WIKI_OPENAI_API_KEY`          | Sent as the API key; many local servers ignore it—default in config is a placeholder.                                                         |
| `WIKI_LLM_MODEL`               | Model id passed to the API (e.g. your Ollama model name).                                                                                     |
| `WIKI_LLM_REQUEST_TIMEOUT_SEC` | Per-request HTTP timeout; long local generations often need **hundreds of seconds**.                                                          |

### LLM “compile” (raw → wiki markdown)

| Variable                       | Purpose                                                                                                                                                     |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WIKI_LLM_COMPILE`             | If `true`, each changed raw `.md` is rewritten through the chat model (Obsidian-oriented prompts) before writing the wiki. Requires `WIKI_OPENAI_API_BASE`. |
| `WIKI_LLM_COMPILE_INCREMENTAL` | If `true`, only re-author files whose **raw** content changed (hash manifest under `data/.wiki-langgraph/` by default).                                     |
| `WIKI_LLM_COMPILE_ENRICH`      | If `true`, merge new raw into **existing** wiki notes instead of full rewrite when a note already exists.                                                   |
| `WIKI_LLM_COMPILE_MAX_WORKERS` | Thread pool size for authoring. **Default `1`**: local servers usually handle one completion at a time; raising this can cause timeouts.                    |
| `WIKI_LLM_COMPILE_REVIEW`      | `off` (default), `risky`, or `all`. `risky` auto-applies low-risk generated notes and queues risky candidates under `data/.wiki-langgraph/candidates/`.      |
| `WIKI_MANIFEST_PATH`           | Optional override for the incremental hash / semantic-cache JSON file. Deleted notes are pruned from stored hashes and semantic caches on later runs.       |

Review queue commands:

```bash
uv run wiki-langgraph review list
uv run wiki-langgraph review show <candidate-id>
uv run wiki-langgraph review approve <candidate-id>
uv run wiki-langgraph review reject <candidate-id>
```

Approving writes the queued markdown to the configured wiki path and records the raw content hash in the manifest so later incremental runs preserve the approved authored note.

Risky candidates include existing-note overwrites, empty or very short output, missing `compiled_from`, large shrinkage, and high wikilink churn. Queued candidates do not update the raw hash in the manifest until approved, so they are retried or remain visible instead of being silently considered done.

### Semantic “See also” / related notes

| Variable                                                             | Purpose                                                                             |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `WIKI_SEMANTIC_LINKS`                                                | If `true`, compile suggests related notes (separate from authored `[[wikilinks]]`). |
| `WIKI_SEMANTIC_BACKEND`                                              | `llm` (needs API base) or `qmd` (local CLI).                                        |
| `WIKI_QMD_BIN`, `WIKI_QMD_COLLECTION`                                | QMD executable and collection name for `qmd query` / refresh.                       |
| `WIKI_QMD_MIN_SCORE`, `WIKI_QMD_TOP_N`, `WIKI_QMD_CANDIDATE_LIMIT`  | Tune retrieval quality and candidate breadth.                                       |
| `WIKI_QMD_NO_RERANK`, `WIKI_QMD_QUERY_TIMEOUT_SEC`                  | Skip reranking for faster CPU-friendly queries and tune query timeouts.             |
| `WIKI_QMD_CHUNK_STRATEGY`                                           | QMD chunking mode for query/embed: `regex` (default) or `auto`.                     |

### QMD index refresh (after compile)

| Variable                       | Purpose                                                                                                                                                                                                                    |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WIKI_QMD_REFRESH`             | If `true`, after writing wiki files run `qmd update` and `qmd embed` for the configured collection. **Default `false`** so a minimal run does not require QMD; enable it when local QMD indexing is installed and desired. |
| `WIKI_QMD_REFRESH_TIMEOUT_SEC`        | Subprocess timeout for refresh.                                                                                                                                                                                            |
| `WIKI_QMD_EMBED_MAX_DOCS_PER_BATCH`   | Optional cap for documents loaded per `qmd embed` batch.                                                                                                                                                                    |
| `WIKI_QMD_EMBED_MAX_BATCH_MB`         | Optional UTF-8 MB cap for each `qmd embed` batch.                                                                                                                                                                          |
| `WIKI_QMD_CPU_ONLY`                   | If `true`, force CPU for node-llama-cpp-backed query/embed work when Metal/GPU fails on macOS.                                                                                                                             |

### Graph runtime

| Variable | Purpose |
| -------- | ------- |
| `WIKI_GRAPH_INGEST_TIMEOUT_SEC` | LangGraph timeout for the ingest node. |
| `WIKI_GRAPH_COMPILE_TIMEOUT_SEC` | LangGraph timeout for compile, including optional local LLM authoring. Default is intentionally high. |
| `WIKI_GRAPH_INDEX_TIMEOUT_SEC` | LangGraph timeout for the index node, including optional QMD refresh/embed. |
| `WIKI_GRAPH_LINT_TIMEOUT_SEC` | LangGraph timeout for vault lint. |

### Lint, logging, skills

| Variable                            | Purpose                                                                                                                                                                     |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WIKI_LINT_ON_RUN`                  | If `true`, run the same checks as `wiki-langgraph lint` after the index step; any issue fails `run` with exit **1**.                                                        |
| `WIKI_LOG_FILE`, `WIKI_LOG_LEVEL`   | Optional file logging; `DEBUG` adds verbose compile detail.                                                                                                                 |
| `WIKI_OBSIDIAN_MARKDOWN_SKILL_PATH` | Optional path to a custom `SKILL.md` for OFM system text; otherwise the bundled package skill is used (or a repo-level `skills/obsidian-markdown/SKILL.md` if you add one). |

For semantics of compile steps and provenance (`compiled_from:`, backlinks vs semantic footers), see **docs/ARCHITECTURE.md** and **AGENTS.md**.

## Link provenance

The generated wiki intentionally keeps three graph concepts separate:

| Section | Meaning |
| --- | --- |
| `See also` | Outbound semantic suggestions from this note to related notes. |
| `Backlinks` | Inbound authored links from other note bodies. Generated `See also` blocks are not counted here. |
| `Related (semantic)` | Inbound semantic suggestions from other notes. These are recommendations, not authored citations. |

This separation prevents machine-suggested relatedness from being mistaken for human/authored evidence.

## Deep Agents

`deep_agent.create_wiki_deep_agent` is available for agent workflows outside the batch compile. It uses the configured chat model, a filesystem backend rooted at the project, bundled/project skills under `/skills/`, `AGENTS.md` memory when present, and filesystem permissions that deny access to `.env`, `.git`, `.codegraph`, and internal agent artifact paths.

The main CLI query and research paths currently use direct LangChain flows for predictability. Deep Agents are best suited for future multi-step agentic research, candidate review assistance, and concept-page synthesis.

## Layout

| Path                  | Role                                             |
| --------------------- | ------------------------------------------------ |
| `data/raw/`           | Source files to ingest (default raw root)        |
| `data/wiki/`          | Compiled vault output (default wiki root)        |
| `Queries/`            | Raw saved-query notes when `query --save` is used |
| `Research/`           | Raw saved research briefs when `research --save` is used |
| `src/wiki_langgraph/` | Package (graph, nodes, linking, lint, LLM hooks) |
| `AGENTS.md`           | Agent-facing project notes                       |

## Tests

```bash
uv run pytest
```

## License

[MIT](LICENSE)
