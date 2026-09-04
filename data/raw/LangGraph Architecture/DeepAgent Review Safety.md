---
type: Note
---

# What prevents a DeepAgent reviewer from changing the vault?

Both DeepAgent review paths run with read-only filesystem permissions. Shared safeguards deny writes and block sensitive project paths such as `.env`, `.git`, and `.codegraph`.

Candidate deep review receives a path allowlist for selected candidate directories, skills, and `AGENTS.md` when present. Its prompt forbids edits and final approval decisions. A human must use the separate review command to approve or reject a candidate.

Knowledge-gap review receives an exact allowlist for the deterministically selected raw/wiki files plus skills and `AGENTS.md`. Findings must cite allowlisted paths that a successful tool result proves were inspected. Duplicate and conflict findings require evidence from two distinct files and an explicit uncertainty statement. Scope limits are reported separately and are not treated as editorial gaps.

## Why this design

The project uses defense in depth: restricted filesystem permissions, explicit read-only prompts, bounded selection, structured response validation, and separate human-controlled actions. A helpful reviewer does not become an unattended publisher.

## Related

- [[DeepAgent Review Role]]
- [[Reliability and Verification]]
