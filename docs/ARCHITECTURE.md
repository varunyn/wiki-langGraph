# wiki-langgraph architecture

Configuration flows through **`Settings`** (`wiki_langgraph.config`) from environment variables and `.env`. See `.env.example` for names.

---

## LangGraph pipeline (`wiki-langgraph run`)

```mermaid
flowchart LR
  START([START]) --> ingest
  ingest[ingest] --> compile_wiki[compile_wiki]
  compile_wiki --> index[index]
  index --> lint[lint]
  lint --> END([END])
```

| Node | Module | What happens |
|------|--------|----------------|
| **ingest** | `nodes.node_ingest` | Recursive file list under **raw** dir → `raw_uris` (skips `.gitkeep`, anything under `.git`). |
| **compile_wiki** | `nodes.node_compile_wiki` | See [Compile step](#compile-step-node_compile_wiki) below. Writes **`index.md`** here. |
| **index** | `nodes.node_index` | Optional **QMD index refresh** only (`QMD` call #2 — see [QMD](#qmd-local-search--embeddings)). Default is effectively off unless `WIKI_QMD_REFRESH=true`. Does **not** write `index.md`. |
| **lint** | `nodes.node_lint` | Runs the same checks as `wiki-langgraph lint` (`lint.run_lint`): unresolved input wikilinks, orphan notes with no outgoing internal links, stale wiki output, `index.md` drift, and OKF concept docs missing required `type` frontmatter. If any issue is reported, sets `last_error` so **`wiki-langgraph run` exits 1**. Skipped when **`WIKI_LINT_ON_RUN=false`**. |

Each graph node is registered as an async LangGraph node with explicit `timeout` and `error_handler` policies. `wiki-langgraph run` remains synchronous at the CLI boundary, but internally uses `ainvoke` so LangGraph can enforce node timeouts. Timeouts are configured with `WIKI_GRAPH_INGEST_TIMEOUT_SEC`, `WIKI_GRAPH_COMPILE_TIMEOUT_SEC`, `WIKI_GRAPH_INDEX_TIMEOUT_SEC`, and `WIKI_GRAPH_LINT_TIMEOUT_SEC`.

### Langfuse tracing

When LANGFUSE_TRACING_ENABLED=true and both Langfuse project keys are set,
observability.py creates a v4 root observation for each run, query, or
research request. Pipeline nodes become child spans, and the LangChain callback
handler records nested LLM generations for authoring, semantic links, queries,
research, and Deep Agents. The integration is opt-in and degrades to a no-op
when credentials are absent.

The standard LANGFUSE_* variables are accepted directly from .env. Use
LANGFUSE_BASE_URL=http://localhost:3300 for the local v4 server; optional
environment and release labels propagate to the observations.

---

## When `WIKI_SEMANTIC_LINKS=true`

This section is the flow **only when semantic links are on**. Otherwise `compile_linked_markdown` skips Pass 1 semantic work and does not persist `semantic_edges`.

Semantic “See also” runs **inside** `compile_linked_markdown` (not a separate LangGraph node). **`node_compile_wiki`** loads the manifest first so **`semantic_cache`** (loaded from `semantic_edges`) can skip LLM/QMD calls when the stripped body hash matches.

```mermaid
flowchart TB
  START([WIKI_SEMANTIC_LINKS = true]) --> LM[load_manifest in node_compile_wiki<br/>semantic_cache ← semantic_edges]
  LM --> CL[compile_linked_markdown]

  subgraph p1["Pass 1 — each .md in catalog"]
    CL --> LOOP[For each rel]
    LOOP --> HASH[SHA256 stripped body]
    HASH --> CACHE{Cache hit?}
    CACHE -->|yes| REUSE[Use cached edges]
    CACHE -->|miss| BR{WIKI_SEMANTIC_BACKEND}
    BR -->|llm| API{WIKI_OPENAI_API_BASE?}
    API -->|yes| LLM[linking_llm.suggest_semantic_related]
    API -->|no| SK[Skip LLM semantic]
    BR -->|qmd| QMD[linking_qmd.suggest_related_via_qmd]
    LLM --> W[semantic_cache rel updated]
    QMD --> W
    REUSE --> AGG[all_semantic]
    SK --> AGG
    W --> AGG
  end

  subgraph p2["Graph + Pass 2"]
    AGG --> FWD[Forward graph = authored [[wikilinks]] only]
    FWD --> BE[Backlinks footer = inverse of forward explicit]
    AGG --> SI[semantic_incoming = reverse of all_semantic]
    BE --> MERGE[Pass 2 write: See also body + Backlinks + Related semantic + frontmatter]
    SI --> MERGE
    MERGE --> OUT[Write wiki files]
  end

  OUT --> SAVE[node_compile_wiki: save_manifest<br/>pruned hashes + pruned semantic_edges]
  SAVE --> IDX[format_index_markdown → index.md]
```

| Setting | Effect |
|---------|--------|
| `WIKI_SEMANTIC_LINKS` | Enables Pass 1 + writes `semantic_edges` back into the manifest at end of compile. |
| `WIKI_SEMANTIC_BACKEND` | `llm` → `linking_llm.suggest_semantic_related`; `qmd` → `linking_qmd.suggest_related_via_qmd` (`qmd query`). |
| `WIKI_OPENAI_API_BASE` | Required for the **LLM** backend; if unset, the LLM branch is skipped (no semantic edges from LLM that run). |

`WIKI_LLM_COMPILE_MAX_WORKERS` does **not** apply here — it only limits **LLM authoring** (`author_raw_to_wiki_markdown`), not Pass 1 semantic calls.

### Provenance (authored links vs semantic)

Obsidian **backlinks** (in the usual sense) are **authored** `[[wikilinks]]`. Semantic similarity is a **recommendation** layer, not the same kind of edge.

| Output | Meaning |
|--------|---------|
| **See also** (body) | Outbound standard Markdown links injected from Pass 1 suggestions — OKF graph edges; still machine-suggested, not hand-written. |
| **Backlinks** (footer) | **Only** notes that contain an authored wikilink targeting this page (computed from explicit extraction only). |
| **Related (semantic)** (footer) | Notes whose suggested See also included **this** page — labeled as compile-time suggestions, distinct from Backlinks. |

Semantic edges are **not** folded into the same forward graph used for Backlinks, so the footer does not treat recommendations as authoritative authored graph edges.

---

## Compile step (`node_compile_wiki`)

Rough order (see `nodes.py` + `linking.py`):

```mermaid
flowchart TB
  subgraph compile["node_compile_wiki"]
    R[raw_uris + dedupe paths] --> M{manifest needed?<br/>llm_compile OR semantic_links}
    M -->|yes| ML[load_manifest<br/>semantic_cache from disk]
    M -->|no| F
    ML --> L{llm_compile?}
    L -->|yes| CH[changed_md_relpaths<br/>from manifest hashes]
    CH --> AU[author_raw_to_wiki_markdown<br/>ThreadPoolExecutor optional]
    AU --> RV{WIKI_LLM_COMPILE_REVIEW}
    RV -->|off or safe| F[compile_linked_markdown]
    RV -->|risky or all queue| Q[data/.wiki-langgraph/candidates]
    L -->|no| F
    Q --> F
    F --> SV{manifest needed?}
    SV -->|yes| SM[prune manifest + update_hashes + save_manifest<br/>semantic_edges when enabled]
    SV -->|no| IDX
    SM --> IDX[format_index_markdown → index.md]
  end
```

| Subsystem | Where | Role |
|-----------|--------|------|
| **Manifest** | `manifest.py` | JSON at `resolved_manifest_path()` (default `data/.wiki-langgraph/manifest.json`): per-file content hashes for incremental **LLM compile**; **`semantic_edges`** cache (hash + list of related relpaths) when **semantic links** are on. Before save, deleted-note hash entries and semantic cache entries are pruned so stale relpaths do not accumulate. |
| **LLM authoring** | `llm_author.py` | Only if `WIKI_LLM_COMPILE=true`: rewrites selected raw `.md` → wiki-shaped markdown; injects `compiled_from:`; optional **enrich** from existing wiki. **Not** parallelized with semantic pass; `WIKI_LLM_COMPILE_MAX_WORKERS` only affects this step. |
| **LLM review queue** | `review_queue.py` + `cli.py` | `WIKI_LLM_COMPILE_REVIEW=off\|risky\|all`. `risky` queues suspicious candidates and existing-note overwrites under `data/.wiki-langgraph/candidates/`; queued notes do not refresh manifest hashes, so they are retried until approved or rejected. CLI commands: `review list`, `review show`, `review approve`, `review reject`. |
| **Knowledge-gap review** | `knowledge_gap_review.py` + `cli.py` | Explicit `review gaps [scope] [--limit N]` action. Resolves a bounded raw/wiki scope, performs deterministic pre-analysis, and invokes the existing read-only DeepAgent with an exact file-level allowlist. Validated findings are rendered as Markdown with coverage and access audit fields; no vault, manifest, QMD, or candidate-queue writes occur. |
| **Linking** | `linking.py` → `compile_linked_markdown` | Process raw markdown into the wiki; leave non-markdown raw assets in place; **Pass 1** semantic suggestions; **explicit-only** forward graph for Backlinks; **Related (semantic)** footer for inbound suggestions; **Pass 2** write; **`frontmatter_graph`** merge (`wiki_langgraph_*` plus OKF `type: Note`); render compiled/generated links as standard Markdown links in the default OKF profile. |
| **Lint** | `lint.py` | **Batch:** `node_lint` after **index** (default). **Ad-hoc:** `wiki-langgraph lint` — same `run_lint` rules (unresolved wikilinks, `W_ORPHAN_NOTE`, `W_INDEX_DRIFT`, `W_STALE_WIKI`, `W_OKF_MISSING_TYPE` when OKF checks are enabled, `E_READ`, etc.). |

---

## QMD (local search / embeddings)

QMD appears in **two independent places**. Both are optional and gated by settings.

### 1) Semantic “See also” backend (`compile_linked_markdown`)

| Setting | Typical value |
|---------|----------------|
| `WIKI_SEMANTIC_LINKS` | `true` |
| `WIKI_SEMANTIC_BACKEND` | `qmd` (vs `llm`) |

| Module | Function |
|--------|----------|
| `linking_qmd.py` | `suggest_related_via_qmd` → runs **`qmd query … --json`** per note (with `qmd_top_n`, `qmd_min_score`, `qmd_candidate_limit`, optional `qmd_no_rerank`, `qmd_chunk_strategy`, and `qmd_query_timeout_sec`), maps `qmd://…` hits back to vault relpaths. |

Invoked from **`linking.py`** inside the **first pass** over markdown notes (same pass as LLM semantic when `semantic_backend=llm`). **Manifest semantic cache** skips `qmd query` when raw body hash unchanged.

**Parallelism:** Semantic work is **per-note inside `compile_linked_markdown`**; it is **not** controlled by `WIKI_LLM_COMPILE_MAX_WORKERS` (that setting only affects LLM authoring in `nodes.py`).

### 2) Index refresh (`graph` node **`index`**)

| Setting | Role |
|---------|------|
| `WIKI_QMD_REFRESH` | When `true`, after wiki files are written, run **`qmd update`** then **`qmd embed -c <collection>`** so the local QMD index/embeddings match the vault on disk. Default is **`false`** so a minimal run does not require QMD. |
| `WIKI_QMD_CHUNK_STRATEGY`, `WIKI_QMD_EMBED_MAX_DOCS_PER_BATCH`, `WIKI_QMD_EMBED_MAX_BATCH_MB` | Optional newer-QMD controls for chunking and embedding memory use. |

| Module | Function |
|--------|----------|
| `linking_qmd.py` | `run_qmd_refresh` (subprocess; `qmd_refresh_timeout_sec`, optional `qmd_cpu_only`/`--no-gpu`, chunk strategy, and embedding batch caps). |

Called only from **`node_index`** — **after** `compile_wiki` finishes, so new/changed wiki paths are on disk before embedding.

---

## LLM (OpenAI-compatible HTTP) — three call sites

All use **`langchain_openai.ChatOpenAI`** with `WIKI_OPENAI_API_BASE`, `WIKI_LLM_MODEL`, `WIKI_LLM_REQUEST_TIMEOUT_SEC`, etc. Authoring reads LangChain message `.text` first, then falls back to provider content blocks, so native reasoning/tool metadata does not leak into compiled markdown.

```mermaid
flowchart TB
  subgraph batch["Batch pipeline compile"]
    A[llm_author.author_raw_to_wiki_markdown<br/>WIKI_LLM_COMPILE] --> B[linking_llm.suggest_semantic_related<br/>semantic_links + backend=llm]
  end
  subgraph interactive["Interactive"]
    C[query.answer_query / query.research_query<br/>ChatOpenAI over retrieved wiki context]
    D[deep_agent.create_wiki_deep_agent<br/>chat_model_from_settings]
  end
```

| Call site | Module | When |
|-----------|--------|------|
| **Authoring** | `llm_author.py` | `WIKI_LLM_COMPILE`: raw → wiki markdown per changed file (incremental via manifest). |
| **Semantic links** | `linking_llm.py` | `WIKI_SEMANTIC_LINKS` and `WIKI_SEMANTIC_BACKEND=llm`: related-note suggestions in `compile_linked_markdown` pass 1. |
| **Query / research** | `query.py` | `wiki-langgraph query` and `wiki-langgraph research`: lexical retrieval over compiled wiki notes, then direct `ChatOpenAI` answer or research brief. |
| **Deep agent** | `deep_agent.py` + `deep_review.py` | Opt-in via `wiki-langgraph agent --deep-review`; reviews queued candidates read-only and is not part of normal `wiki run` or `agent` execution. |

**Obsidian OFM system text** for prompts: `obsidian_prompt.wiki_llm_system_instructions` / `load_obsidian_markdown_skill_text` (skill path: `WIKI_OBSIDIAN_MARKDOWN_SKILL_PATH` or project/bundled `skills/obsidian-markdown/SKILL.md`).

---

## `compile_linked_markdown` internals (`linking.py`)

1. Load all `.md` bodies (or **content_overrides** from LLM step). OKF-reserved `index.md` and `log.md` files are preserved as reserved files, not treated as concepts.
2. **Pass 1 — semantic edges (if enabled):** for each concept `.md`, body hash vs **semantic_cache** → if miss, call **`suggest_semantic_related`** (LLM) or **`suggest_related_via_qmd`** (QMD).
3. Build **forward_explicit** from **`extract_wikilink_targets` only**; **backlinks_explicit** = inverse. Build **semantic_incoming** from `all_semantic` (reverse edges). Do **not** merge semantic stems into the forward graph used for Backlinks.
4. **Pass 2 — write:** strip managed blocks, merge **`wiki_langgraph_*`** and OKF `type: Note`; convert resolved input wikilinks to standard Markdown links in OKF output using paths relative to the source note; append **See also** + **Backlinks** (authored) + **Related (semantic)** (inbound suggestions), with dedupe so a neighbor is not listed twice on the same page when already in See also.
5. Return counts; caller prunes stale manifest entries, saves fresh hashes / semantic cache, and writes **index.md**.

The default OKF profile writes the reserved lowercase `index.md` with `okf_version: "0.2"`. On filesystems that preserve legacy `Index.md` casing, compile renames the old generated file through a temporary name first so the directory entry becomes canonical lowercase. Any `log.md` at any directory level is copied unchanged and is excluded from the concept index and graph.

---

## CLI

### Bounded agent controller

`wiki-langgraph agent` is a deliberately bounded control loop around the existing graph:

```mermaid
flowchart LR
  I[inspect raw files, manifest, review queue] --> P[deterministic plan]
  P -->|--dry-run| O[report plan]
  P -->|execute, at most N times| A[run graph]
  A --> V[verify graph state and lint result]
  V --> R[replan from fresh inspection]
  R -->|safe next action| P
  R -->|no safe action| O[report outcome]
```

The controller does not ask an LLM to invent shell commands or retry indefinitely. `--max-iterations`
sets the hard iteration bound (two by default). `--only` and
`--limit` constrain LLM authoring, while deterministic compilation still processes the complete raw
corpus. Agent verification reports warnings but fails on lint errors. Normal `run` behavior remains
strict for backward compatibility. Use `wiki-langgraph agent --dry-run` to inspect the proposed action
before allowing writes or AI calls.

`--deep-review` is the explicit DeepAgent boundary. It reads up to three queued review candidates,
is read-scoped to those candidate directories plus skills/memory, returns recommendations for a
human, and is denied filesystem writes. It does not run for ordinary agent invocations and does not
approve or reject candidates.

| Command | Flow |
|---------|------|
| `wiki-langgraph run` | `graph.run_once` → ingest → compile_wiki → index → **lint** (unless `WIKI_LINT_ON_RUN=false`). On lint failure, stderr shows `last_error` + step log; exit **1**. |
| `wiki-langgraph agent` | Inspect → plan → run → verify → replan, bounded by `--max-iterations`. `--dry-run` stops after inspection; `--only`/`--limit` bound optional LLM authoring. |
| `wiki-langgraph agent --deep-review` | Read-only DeepAgent review of queued candidates; human approval is still required. |
| `wiki-langgraph query "..." [--save]` | Local lexical retrieval over compiled wiki notes → `ChatOpenAI` answer. `--save` writes a raw note under `Queries/` with source wikilinks; the next `run` compiles it into the wiki. |
| `wiki-langgraph research "..." [--save]` | Same retrieval layer as `query`, with a larger default context window and a structured research-brief prompt. `--save` writes a raw note under `Research/` with source wikilinks; the next `run` compiles it into the wiki. |
| `wiki-langgraph review list/show/approve/reject` | Inspect or resolve pending LLM compile candidates from `data/.wiki-langgraph/candidates/`. Approve writes the candidate markdown to the wiki target and updates the raw hash in the manifest. |
| `wiki-langgraph review gaps [scope] [--limit N]` | Run the separate bounded, read-only editorial review. Scope is a relative Markdown file/directory; output exposes normalized scope, reviewed paths, omissions, and read allowlist before deterministic Markdown findings. |
| `wiki-langgraph lint` | `lint.run_lint` on raw + wiki only (no compile). Same rules as the **lint** graph node, including orphan-note warnings for notes with no outgoing internal links; optional `--strict` treats warnings as exit **1** when used standalone. |
| `wiki-langgraph lint --fix` | `lint.fix_unresolved_wikilinks`: rewrite broken `[[links]]` in **raw** `.md` (fuzzy catalog match, then strip to plain text unless `--fix-mode rewrite`). Use `--dry-run` first. |
| `wiki-langgraph version` | Package version string. |

**Exit behavior:** the graph **lint** node fails the run if **`run_lint`** returns **any** issue. The standalone **`lint`** command exits **0** when there are only warnings unless you pass **`--strict`** (then warnings also fail).

---

## Deep Agents (separate from batch compile)

| Piece | Role |
|-------|------|
| `deep_agent.create_wiki_deep_agent` | LangGraph Deep Agent with filesystem backend; **`/skills/`** routes to bundled `wiki_langgraph/skills` or project `skills/` when `skills/obsidian-markdown/SKILL.md` exists. Loads `/AGENTS.md` as Deep Agents memory when present, and denies filesystem-tool access to `.env`, `.git`, `.codegraph`, and internal agent artifact paths. |
| Not invoked by `wiki-langgraph run`. | |

---

## Quick reference: “where is X?”

| Concern | Primary location |
|---------|-------------------|
| Graph topology | `graph.py` |
| State + reducers | `state.py` |
| Ingest / compile / index / lint nodes | `nodes.py` |
| Wikilinks, backlinks, See also, frontmatter merge | `linking.py`, `frontmatter_graph.py` |
| QMD query + refresh | `linking_qmd.py` |
| LLM semantic suggestions | `linking_llm.py` |
| LLM raw→wiki authoring | `llm_author.py` |
| Incremental hashes + semantic cache | `manifest.py` |
| Env / validation | `config.py` |
| Vault lint rules | `lint.py` |
