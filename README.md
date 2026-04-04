# wiki-langgraph

LangGraph pipeline that **ingests** raw markdown, **compiles** an Obsidian-style vault (wikilinks, backlinks, `Index.md`), optionally runs **LLM authoring** and **semantic “See also”** links, refreshes a local **[QMD](https://github.com/tobi/qmd)** index when enabled, and **lints** the vault.

## Background: the “LLM Wiki” pattern

Andrej Karpathy [posted on X](https://x.com/karpathy/status/2039805659525644595) about a workflow where the model does not only retrieve chunks at question time (classic RAG), but **incrementally builds and maintains a persistent, interlinked markdown wiki** between you and your raw sources—so structure and synthesis **compound** instead of being re-derived every query. He expanded the idea in a copy-paste **idea file**, **[llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)).

**wiki-langgraph** is a **concrete implementation** of parts of that pattern: a reproducible compile pipeline, vault linking, optional LLM passes, optional local search/embeddings via QMD, and rule-based lint. The gist stays intentionally abstract; this repo pins directory layout, env vars, and graph behavior—see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full node graph and module map.

## Prerequisites

| Requirement | When you need it |
|-------------|------------------|
| **Python 3.12+** | Always |
| **[uv](https://docs.astral.sh/uv/)** | Always (install deps and run the CLI) |
| **OpenAI-compatible HTTP API** (`WIKI_OPENAI_API_BASE`) | `WIKI_LLM_COMPILE=true` and/or `WIKI_SEMANTIC_LINKS=true` with `WIKI_SEMANTIC_BACKEND=llm` (e.g. [Ollama](https://ollama.com/) with OpenAI compatibility, llama.cpp server, vLLM, etc.) |
| **[QMD](https://github.com/tobi/qmd)** on `PATH` | `WIKI_SEMANTIC_BACKEND=qmd` and/or `WIKI_QMD_REFRESH=true` (hybrid search + optional `qmd embed` after compile) |
| **Obsidian** | Optional; useful as the reader/UI for the generated vault, not required to run the pipeline |

**Minimal run:** no `.env` required if you are fine with defaults `data/raw` → `data/wiki` under the repo and you do not enable LLM compile or semantic LLM features. Anything that calls the chat API needs a reachable base URL and model id.

## Setup

```bash
uv sync
cp .env.example .env   # optional; set paths and features below
```

Settings load from the environment with prefix **`WIKI_`** (and optional **`.env`** in the current working directory). **`cp .env.example .env`** is the usual starting point; adjust only what you use.

## Run

```bash
uv run wiki-langgraph run -v
uv run wiki-langgraph lint
uv run wiki-langgraph version
```

### Fixing unresolved `[[wikilinks]]` in raw notes

Lint only sees links that resolve **within your ingested raw tree**. To clean notes automatically:

```bash
uv run wiki-langgraph lint --fix --dry-run   # preview: fuzzy rewrites + strip the rest
uv run wiki-langgraph lint --fix             # edit raw .md under WIKI_DATA_RAW_DIR
uv run wiki-langgraph lint --fix --fix-mode strip    # plain text only (no fuzzy rename)
uv run wiki-langgraph lint --fix --fix-mode rewrite  # fuzzy only; leave what is still broken
```

**`--fix`** updates **raw** sources: it tries a **single unambiguous fuzzy match** to a catalog note label (`difflib`, configurable `--fuzzy-cutoff`), then turns any remaining broken links into **plain text** (keeping `[[note|alias]]` as `alias`). Re-run **`wiki-langgraph run`** so the wiki matches. It does **not** invent files for links that point outside your corpus—those become plain text unless fuzzy finds a close in-vault name.

## Configuration (environment variables)

All names are listed in **`.env.example`**. Below is what matters and when to set it.

### Paths and project layout

| Variable | Purpose |
|----------|---------|
| `WIKI_DATA_RAW_DIR` | Root folder to **ingest** (recursive). Default: `<project>/data/raw`. |
| `WIKI_DATA_WIKI_DIR` | **Compiled vault** output. Default: `<project>/data/wiki`. Set this when your vault lives inside a larger Obsidian tree; see `.env.example` for avoiding duplicated `wiki/wiki/` path segments. |

If unset, paths are derived from the package location (repo root when developing).

### OpenAI-compatible LLM (chat HTTP)

| Variable | Purpose |
|----------|---------|
| `WIKI_OPENAI_API_BASE` | Base URL for chat completions, e.g. `http://127.0.0.1:11434/v1` (Ollama). **Required** when `WIKI_LLM_COMPILE` or semantic LLM backend is on. |
| `WIKI_OPENAI_API_KEY` | Sent as the API key; many local servers ignore it—default in config is a placeholder. |
| `WIKI_LLM_MODEL` | Model id passed to the API (e.g. your Ollama model name). |
| `WIKI_LLM_REQUEST_TIMEOUT_SEC` | Per-request HTTP timeout; long local generations often need **hundreds of seconds**. |

### LLM “compile” (raw → wiki markdown)

| Variable | Purpose |
|----------|---------|
| `WIKI_LLM_COMPILE` | If `true`, each changed raw `.md` is rewritten through the chat model (Obsidian-oriented prompts) before writing the wiki. Requires `WIKI_OPENAI_API_BASE`. |
| `WIKI_LLM_COMPILE_INCREMENTAL` | If `true`, only re-author files whose **raw** content changed (hash manifest under `data/.wiki-langgraph/` by default). |
| `WIKI_LLM_COMPILE_ENRICH` | If `true`, merge new raw into **existing** wiki notes instead of full rewrite when a note already exists. |
| `WIKI_LLM_COMPILE_MAX_WORKERS` | Thread pool size for authoring. **Default `1`**: local servers usually handle one completion at a time; raising this can cause timeouts. |
| `WIKI_MANIFEST_PATH` | Optional override for the incremental hash / semantic-cache JSON file. |

### Semantic “See also” / related notes

| Variable | Purpose |
|----------|---------|
| `WIKI_SEMANTIC_LINKS` | If `true`, compile suggests related notes (separate from authored `[[wikilinks]]`). |
| `WIKI_SEMANTIC_BACKEND` | `llm` (needs API base) or `qmd` (local CLI). |
| `WIKI_QMD_BIN`, `WIKI_QMD_COLLECTION` | QMD executable and collection name for `qmd query` / refresh. |
| `WIKI_QMD_MIN_SCORE`, `WIKI_QMD_TOP_N`, `WIKI_QMD_QUERY_TIMEOUT_SEC` | Tune retrieval quality and timeouts. |

### QMD index refresh (after compile)

| Variable | Purpose |
|----------|---------|
| `WIKI_QMD_REFRESH` | If `true`, after writing wiki files run `qmd update` and `qmd embed` for the configured collection. Set `false` in CI or when QMD is not installed. |
| `WIKI_QMD_REFRESH_TIMEOUT_SEC` | Subprocess timeout for refresh. |
| `WIKI_QMD_CPU_ONLY` | If `true`, force CPU for node-llama-cpp-backed embedders when Metal/GPU fails on macOS. |

### Lint, logging, skills

| Variable | Purpose |
|----------|---------|
| `WIKI_LINT_ON_RUN` | If `true`, run the same checks as `wiki-langgraph lint` after the index step; any issue fails `run` with exit **1**. |
| `WIKI_LOG_FILE`, `WIKI_LOG_LEVEL` | Optional file logging; `DEBUG` adds verbose compile detail. |
| `WIKI_OBSIDIAN_MARKDOWN_SKILL_PATH` | Optional path to a custom `SKILL.md` for OFM system text; otherwise the bundled package skill is used (or a repo-level `skills/obsidian-markdown/SKILL.md` if you add one). |

For semantics of compile steps and provenance (`compiled_from:`, backlinks vs semantic footers), see **docs/ARCHITECTURE.md** and **AGENTS.md**.

## Layout

| Path | Role |
|------|------|
| `data/raw/` | Source files to ingest (default raw root) |
| `data/wiki/` | Compiled vault output (default wiki root) |
| `src/wiki_langgraph/` | Package (graph, nodes, linking, lint, LLM hooks) |
| `AGENTS.md` | Agent-facing project notes |

## Tests

```bash
uv run pytest
```

## License

[MIT](LICENSE)
