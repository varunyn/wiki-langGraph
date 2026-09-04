---
title: QMD 2.8.3 Integration Review
note_type: research
project: wiki-langgraph
status: reviewed
tags:
  - qmd
  - integration
  - research
---

# QMD 2.8.3 Integration Review

## Purpose

Review the latest QMD release and decide whether its changes justify modifying the wiki pipeline.

## Findings

- QMD v2.8.3 is the latest release reviewed on 2026-08-25.
- The repository already used newer query controls including candidate limits, chunk strategy, and embedding batch caps.
- Most relevant changes are upstream security and correctness fixes: project-local configuration trust gates, filesystem containment, safer concurrent query/embed behavior, and index cleanup improvements.
- `--full-path` predates v2.8.3. The release improves its stale-result fallback and diagnostics rather than introducing the option.
- Enabling `--full-path` by default would add a QMD-version compatibility requirement and route normal results through ambiguous suffix matching without evidence that the current `qmd://` mapping is failing.

## Decision

- Keep the existing stable `qmd query --json` contract and exact virtual-path mapping.
- Recommend QMD v2.8.3 or newer to benefit from upstream security and reliability fixes.
- Add a result-mode feature only after reproducing a concrete mapping problem and testing against a real QMD installation.

## Verification

- Existing mocked QMD integration tests pass.
- Full QMD execution was not possible because the `qmd` executable is not installed in this environment.

## Sources

- [QMD v2.8.3 release notes](https://github.com/tobi/qmd/releases/tag/v2.8.3)
- [QMD v2.8.3 usage documentation](https://raw.githubusercontent.com/tobi/qmd/v2.8.3/README.md)

## Related Notes

- [[Wiki Pipeline and OKF Evolution]]
