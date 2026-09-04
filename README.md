# wiki-langgraph

`wiki-langgraph` turns a folder of Markdown notes into a linked, searchable
Markdown wiki. It is a Python 3.12+ LangGraph pipeline with a deterministic
core and optional local AI features.

The important idea is simple:

```text
raw Markdown  →  compile  →  linked wiki  →  query / research
                     │
                     └─ optional LLM authoring, semantic links, and QMD indexing
```

The generated wiki uses the [Open Knowledge Format (OKF)](https://open-knowledge-format.org/)
by default, so it can be opened in Obsidian or another Markdown tool.

## Choose your starting point

| You want to… | Start here |
| --- | --- |
| Compile raw notes into a wiki | [Quick start](#quick-start) |
| See what would happen before writing | [`run --plan`](#preview-before-you-run) |
| Ask questions over the compiled wiki | [Query and research](#query-and-research) |
| Add AI-written notes or summaries | [Optional AI features](#optional-ai-features) |
| Fix broken links or stale output | [Lint and fix](#lint-and-fix) |
| Understand the graph and file flow | [How it works](#how-it-works) |
| Find every setting | [Configuration](#configuration) |

## What it does

- Recursively reads raw `.md` files from `data/raw/`.
- Writes compiled notes to `data/wiki/`.
- Adds frontmatter, provenance, standard Markdown navigation links, authored backlinks, and a generated `index.md`.
- Keeps authored links separate from machine-suggested semantic links.
- Optionally uses an OpenAI-compatible chat endpoint for note authoring, queries, research briefs, and semantic links.
- Optionally uses [QMD](https://github.com/tobi/qmd) for semantic retrieval and local index/embed refresh.
- Lints unresolved input wikilinks, orphan notes, stale output, OKF frontmatter, and index drift.
- Saves useful query and research results back into the raw vault so they become future context.
- Provides a bounded, read-only knowledge-gap review for missing, duplicated, or weakly connected concepts.

`wiki-langgraph` does not require an LLM or QMD for its basic compile path.

## Quick start

### 1. Install

Requirements:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

From the repository root:

```bash
uv sync
```

### 2. Add raw notes

Put Markdown files anywhere under `data/raw/`:

```text
data/raw/
├── projects/
│   └── wiki-langgraph.md
└── concepts/
    └── retrieval.md
```

The default directories are `data/raw/` for source notes and `data/wiki/` for
generated output. You can change them with `WIKI_DATA_RAW_DIR` and
`WIKI_DATA_WIKI_DIR`.

### 3. Compile

```bash
uv run wiki-langgraph run -v
```

This runs:

```text
ingest → compile → optional QMD refresh → lint
```

Open `data/wiki/` in Obsidian or any Markdown-compatible tool after the run.
The default output profile is OKF. To preserve the legacy Obsidian-style
output, set `WIKI_OUTPUT_PROFILE=obsidian`.

### 4. Inspect the result

```bash
uv run wiki-langgraph lint
uv run wiki-langgraph version
```

The generated `data/wiki/index.md` is the registry of compiled notes. It is
regenerated on every compile, even when individual notes have not changed.

## Preview before you run

Use `--plan` when you want to inspect the corpus and estimated AI work without
writing files or calling APIs:

```bash
uv run wiki-langgraph run --plan
```

`--only` and `--limit` constrain optional LLM authoring only. The deterministic
compiler still sees the complete raw corpus so link resolution and `index.md`
remain complete:

```bash
uv run wiki-langgraph run --plan \
  --only 'projects/**/*.md' \
  --limit 5
```

## Command reference

### Build and inspect

| Command | What it does |
| --- | --- |
| `uv run wiki-langgraph run` | Run ingest, compile, optional QMD refresh, and lint. |
| `uv run wiki-langgraph run -v` | Run with step logging. |
| `uv run wiki-langgraph run --plan` | Preview selected files and AI work without writing or calling APIs. |
| `uv run wiki-langgraph agent --dry-run` | Inspect the workspace and show a bounded proposed action. |
| `uv run wiki-langgraph agent` | Run the bounded inspect → plan → act → verify → replan loop. |
| `uv run wiki-langgraph agent --deep-review` | Opt into read-only review of queued AI candidates. |
| `uv run wiki-langgraph eval` | Run the reviewed hosted research-v1 baseline through Langfuse. |
| `uv run wiki-langgraph agent-eval` | Evaluate the bounded agent on isolated fixtures. |
| `uv run wiki-langgraph gap-eval` | Evaluate the local draft knowledge-gap dataset on isolated fixtures. |
| `uv run wiki-langgraph version` | Print the package version. |

The bounded `agent` command runs two iterations by default and stops for
manual review when there is no safe automatic action. Use
`--max-iterations N` to change the bound.

### Query and research

These commands use the compiled wiki as context and require an OpenAI-compatible
chat endpoint configured through `WIKI_OPENAI_API_BASE`.

```bash
uv run wiki-langgraph query "How should I debug RAG failures?"
uv run wiki-langgraph research "Compare RAG failures and evaluation loops"
```

Use `--save` to write the result into the raw vault:

```bash
uv run wiki-langgraph query "How should I debug RAG failures?" --save
uv run wiki-langgraph research "Compare RAG failures and evaluation loops" --save
uv run wiki-langgraph run -v
```

Saved notes are sources of truth in the raw vault. They compile into generated
pages on the next run:

```text
raw:       data/raw/Queries/<question>.md
generated: data/wiki/Queries/<question>.md

raw:       data/raw/Research/<question>.md
generated: data/wiki/Research/<question>.md
```

`query` uses the top five retrieved notes by default; `research` uses the top
eight. Change either with `--top-k N`.

### Review AI-generated candidates

Set `WIKI_LLM_COMPILE_REVIEW=risky` or `all` to queue generated notes for
manual review instead of writing every candidate directly:

```bash
uv run wiki-langgraph review list
uv run wiki-langgraph review show <candidate-id>
uv run wiki-langgraph review approve <candidate-id>
uv run wiki-langgraph review reject <candidate-id>
```

Approval writes the candidate to the configured wiki path and records it in the
incremental manifest.

### Knowledge-gap review

Use `review gaps` for an advisory editorial pass over the local raw and compiled corpus:

```bash
uv run wiki-langgraph review gaps
uv run wiki-langgraph review gaps Architecture/ --limit 12
```

The optional scope is a Markdown file or directory relative to both configured roots. The review
is bounded (24 logical notes by default, up to 100), read-only, and never writes notes, manifests,
QMD state, or the candidate queue. Its Markdown report includes evidence-backed findings such as
missing concept notes, weak connections, possible duplicates or conflicts, missing overviews, and
source-to-wiki coverage concerns. Before the report, the command prints an audit of normalized
scope, reviewed paths, omitted notes, and the file-level read allowlist. A partial review is clearly
marked and should be narrowed before treating it as a corpus-wide assessment.


## Optional AI features

The base compile path is deterministic. Enable only the capability you need.

### LLM authoring: raw notes → authored wiki Markdown

Set an OpenAI-compatible endpoint and enable compilation:

```dotenv
WIKI_OPENAI_API_BASE=http://127.0.0.1:11434/v1
WIKI_LLM_MODEL=your-model
WIKI_LLM_COMPILE=true
```

Ollama, llama.cpp servers, vLLM, and other compatible servers can be used.
Authoring is incremental by default: only raw notes whose content changed are
sent to the model. The manifest is stored at
`data/.wiki-langgraph/manifest.json` by default.

Useful controls:

```dotenv
WIKI_LLM_COMPILE_INCREMENTAL=true
WIKI_LLM_COMPILE_ENRICH=false
WIKI_LLM_COMPILE_MAX_WORKERS=1
WIKI_LLM_COMPILE_REVIEW=off   # off, risky, or all
```

`WIKI_LLM_COMPILE_MAX_WORKERS` defaults to `1` because local servers often
process one completion at a time.

### Semantic links: “See also”

Semantic links are recommendations, not authored citations:

```dotenv
WIKI_SEMANTIC_LINKS=true
WIKI_SEMANTIC_BACKEND=llm    # llm or qmd
```

The generated wiki keeps these concepts separate:

| Output | Meaning |
| --- | --- |
| `Backlinks` | Inbound links created by authored `[[wikilinks]]` only. |
| `See also` | Outbound machine-suggested related notes. |
| `Related (semantic)` | Inbound machine-suggested relationships. |

This prevents similarity recommendations from being mistaken for authored
evidence.

### QMD search and refresh

QMD has two independent uses. Install QMD and put it on `PATH` if you use
either one.

1. Semantic related-note suggestions:

   ```dotenv
   WIKI_SEMANTIC_LINKS=true
   WIKI_SEMANTIC_BACKEND=qmd
   WIKI_QMD_COLLECTION=cursor
   ```

2. Refreshing the local QMD index after compilation:

   ```dotenv
   WIKI_QMD_REFRESH=true
   ```

`WIKI_QMD_REFRESH` is off by default. It runs `qmd update` and `qmd embed`
after wiki files are written. Do not confuse this refresh with the QMD
semantic-link backend; they are separate paths.

## Lint and fix

Run checks without compiling:

```bash
uv run wiki-langgraph lint
uv run wiki-langgraph lint --strict
```

Lint checks for:

- unresolved `[[wikilinks]]` in raw notes
- orphan notes with no outgoing authored internal links
- raw notes newer than their compiled output
- drift in `index.md`
- missing OKF `type` frontmatter
- file read errors

To clean unresolved raw wikilinks, preview first:

```bash
uv run wiki-langgraph lint --fix --dry-run
uv run wiki-langgraph lint --fix
```

By default, `--fix` tries one unambiguous fuzzy match and turns anything still
broken into plain text. Other modes are available:

```bash
uv run wiki-langgraph lint --fix --fix-mode strip    # plain text only
uv run wiki-langgraph lint --fix --fix-mode rewrite  # fuzzy rewrites only
```

Fixes edit raw Markdown, not generated wiki files. Run `wiki-langgraph run`
afterward to regenerate the wiki.

## Configuration

Settings use the `WIKI_` environment prefix and load an optional `.env` file
from the current working directory. Copy the example file to get started:

```bash
cp .env.example .env
```

### Paths and output

| Variable | Default / purpose |
| --- | --- |
| `WIKI_DATA_RAW_DIR` | Raw input root; defaults to `data/raw`. |
| `WIKI_DATA_WIKI_DIR` | Generated wiki root; defaults to `data/wiki`. |
| `WIKI_OUTPUT_PROFILE` | `okf` by default, or `obsidian` for legacy output. |
| `WIKI_MANIFEST_PATH` | Optional incremental manifest override. |
| `WIKI_LINT_ON_RUN` | `true` by default; set `false` to skip lint after `run`. |

If the wiki directory is inside the raw directory, it is excluded from ingest
so generated pages do not become raw input. The generated registry is always
lowercase `index.md`; a legacy `Index.md` is migrated before writing.

### OpenAI-compatible chat endpoint

| Variable | Purpose |
| --- | --- |
| `WIKI_OPENAI_API_BASE` | Required for `query`, `research`, LLM authoring, and LLM semantic links. |
| `WIKI_OPENAI_API_KEY` | API key; local servers commonly ignore it. |
| `WIKI_LLM_MODEL` | Model identifier; defaults to `local`. |
| `WIKI_LLM_REQUEST_TIMEOUT_SEC` | Per-request timeout; defaults to 300 seconds. |

### LLM authoring

| Variable | Purpose |
| --- | --- |
| `WIKI_LLM_COMPILE` | Rewrite changed raw notes with the chat model. Default `false`. |
| `WIKI_LLM_COMPILE_INCREMENTAL` | Re-author only changed notes. Default `true`. |
| `WIKI_LLM_COMPILE_ENRICH` | Merge new source into an existing note instead of replacing it. |
| `WIKI_LLM_COMPILE_MAX_WORKERS` | Authoring concurrency. Default `1`. |
| `WIKI_LLM_COMPILE_REVIEW` | `off`, `risky`, or `all`. |
| `WIKI_OBSIDIAN_MARKDOWN_SKILL_PATH` | Optional custom Markdown/Obsidian instructions for LLM authoring. |

### Langfuse tracing

When the three project variables below are configured, wiki-langgraph sends
v4 observations to the local or remote Langfuse server. The integration uses
the Langfuse Python SDK v4 and LangChain callback handler, so a wiki.run
trace contains the ingest, compile, index, and lint steps plus nested LLM
generations from authoring, semantic links, queries, research, and Deep Agents. Query and research
retrieval is recorded as a `RETRIEVER` observation with the selected source paths.
Tracing is disabled automatically when the keys are absent.

| Variable | Purpose |
| --- | --- |
| LANGFUSE_PUBLIC_KEY | Langfuse project public key. |
| LANGFUSE_SECRET_KEY | Langfuse project secret key; keep it out of Git. |
| LANGFUSE_BASE_URL | Langfuse API base URL, for example http://localhost:3300. |
| LANGFUSE_TRACING_ENABLED | Enable/disable tracing; defaults to false to avoid accidental data export. |
| LANGFUSE_TRACING_ENVIRONMENT | Optional environment label, such as development. |
| LANGFUSE_TRACING_RELEASE | Optional release label for comparing runs. |
| OTEL_SERVICE_NAME | OpenTelemetry service name; defaults to `wiki-langgraph`. |

Short-lived query, research, and evaluation commands explicitly flush the SDK exporter before
returning. Open the Langfuse Traces view at http://localhost:3300 to
inspect the resulting observation tree.

### Semantic links and QMD tuning

| Variable | Purpose |
| --- | --- |
| `WIKI_SEMANTIC_LINKS` | Enable semantic related-note suggestions. Default `false`. |
| `WIKI_SEMANTIC_BACKEND` | `llm` or `qmd`. |
| `WIKI_QMD_BIN` | QMD executable; defaults to `qmd`. |
| `WIKI_QMD_COLLECTION` | QMD collection name. |
| `WIKI_QMD_MIN_SCORE` | Minimum relatedness score; default `0.35`. |
| `WIKI_QMD_TOP_N` | Number of QMD results to consider; default `10`. |
| `WIKI_QMD_CANDIDATE_LIMIT` | Candidate breadth; default `40`. |
| `WIKI_QMD_NO_RERANK` | Skip reranking for faster CPU-friendly queries. |
| `WIKI_QMD_QUERY_TIMEOUT_SEC` | Semantic query timeout; default `120` seconds. |
| `WIKI_QMD_REFRESH` | Run `qmd update` and `qmd embed` after compile. Default `false`. |
| `WIKI_QMD_REFRESH_TIMEOUT_SEC` | Refresh timeout; default `600` seconds. |
| `WIKI_QMD_CHUNK_STRATEGY` | `regex` or `auto`. |
| `WIKI_QMD_CPU_ONLY` | Disable GPU use for QMD when GPU initialization fails. |

Graph node timeouts are configurable with
`WIKI_GRAPH_INGEST_TIMEOUT_SEC`, `WIKI_GRAPH_COMPILE_TIMEOUT_SEC`,
`WIKI_GRAPH_INDEX_TIMEOUT_SEC`, and `WIKI_GRAPH_LINT_TIMEOUT_SEC`.

All available settings and example values are listed in [`.env.example`](.env.example).

## How it works

The normal pipeline is:

```text
1. Ingest       discover raw Markdown recursively
2. Compile      write linked notes and regenerate index.md
3. Index        optionally refresh QMD
4. Lint         report errors and warnings
```

The compiled wiki preserves provenance with `compiled_from:` frontmatter and
adds OKF `type: Note` frontmatter to concept notes. Generated navigation uses
standard Markdown links in the default OKF profile.

For the complete node graph, manifest behavior, semantic-link flow, and module
map, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Project layout

```text
data/raw/                 source Markdown
data/wiki/                generated wiki
data/.wiki-langgraph/     manifest and review candidates
src/wiki_langgraph/       package implementation
tests/                    pytest suite
docs/ARCHITECTURE.md      detailed pipeline design
.env.example              configuration reference
```

## Development

Run the test suite with:

```bash
uv run pytest
```

Run focused tests while changing a subsystem, for example:

```bash
uv run pytest tests/test_linking.py
uv run pytest tests/test_lint.py
uv run pytest tests/test_query.py
```

## Background

This project implements part of the “LLM Wiki” pattern: instead of retrieving
chunks only at question time, maintain a persistent, interlinked Markdown wiki
whose structure and synthesis compound over time. The idea was described by
[Andrej Karpathy](https://x.com/karpathy/status/2039805659525644595) and in
his [idea file](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## License

[MIT](LICENSE)
