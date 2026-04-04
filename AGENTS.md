## Learned User Preferences

- Prefer the wiki compile step to always regenerate `Index.md` on each pipeline run so the wiki reflects current ingest, not only when the file was missing.
- When writing tests for this repo, set `Settings` with explicit `data_raw_dir` and `data_wiki_dir` under a temporary path so a developer `.env` does not point tests at real vault paths.
- When improving the pipeline, prioritize linting and treating LLM “compile” as incremental wiki authoring.
- When validating automated wiki output, treat notes with **no outgoing wikilinks** as suspect—prefer lint or pipeline rules that flag or drop them when raw/source data may be wrong.

## Learned Workspace Facts

- wiki-langgraph ingests the configured raw directory recursively; `raw_uris` are posix paths relative to that root, and ingest skips `.gitkeep` and files under `.git`.
- Compile copies sources into the wiki tree, parses Obsidian `[[wikilinks]]`, appends a managed **Backlinks** section (wrapped in HTML comment markers for safe replacement), and rebuilds `Index.md` with wikilinks to each markdown note.
- Obsidian OFM skill resolves in order: `WIKI_OBSIDIAN_MARKDOWN_SKILL_PATH` if set, else project `skills/obsidian-markdown/SKILL.md`, else bundled `wiki_langgraph/skills/obsidian-markdown/SKILL.md`. `references/*.md` ship with the bundled skill; add a repo-level `skills/` tree only when overriding. `wiki_llm_system_instructions` / `load_obsidian_markdown_skill_text` supply plain-chat system text (frontmatter stripped by default).
- Deep Agents integration uses `create_wiki_deep_agent` with `skills=["/skills/"]` and a filesystem backend that composites bundled package skills under `/skills/` when the project has no repo-level `skills/obsidian-markdown/SKILL.md`.
- When `llm_compile` is on, `WIKI_LLM_COMPILE_MAX_WORKERS` defaults to **1** (sequential): local OpenAI-compatible servers usually run one completion at a time; raising workers can queue requests and cause mass HTTP timeouts. Increase only if the server truly supports concurrent completions.
- Semantic edge / related-note work during compile happens inside `compile_linked_markdown` (per note) and is not sped up by `WIKI_LLM_COMPILE_MAX_WORKERS`, which applies only to the LLM authoring pass.
- **Authored wikilinks** drive the explicit forward graph used for **Backlinks**; semantic “See also” / related suggestions (`semantic_edges` in the manifest when `WIKI_SEMANTIC_LINKS` is on) are a separate provenance layer—do not treat them like Obsidian backlink edges.
