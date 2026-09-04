---
type: Note
---

# What are the stages of the LangGraph pipeline?

The normal LangGraph workflow is a fixed sequence:

1. **Ingest** finds raw files and records their relative paths.
2. **Compile wiki** writes the linked wiki, managed frontmatter, and `index.md`.
3. **Index** optionally refreshes QMD search and embeddings.
4. **Lint** checks the raw/wiki pair for broken links, stale output, index drift, and other health issues.

Each stage has an explicit timeout and error handler. The pipeline does not choose its own steps or change its topology at runtime.

## Why this shape

Separating discovery, compilation, optional indexing, and validation keeps the minimal path free of LLM and QMD requirements while preserving clear operational boundaries.

## Related

- [[Graph State]]
- [[Reliability and Verification]]
