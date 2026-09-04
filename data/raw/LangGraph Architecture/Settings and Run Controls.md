---
type: Note
---

# How are settings kept separate from graph state?

The graph is built with a `Settings` object that supplies paths, timeouts, and feature flags to the node wrappers. Per-run controls such as LLM selection patterns, LLM limits, and lint strictness are placed in the initial graph state.

## Why this design

Settings describe how the system is configured to run. Graph state describes what happened during one run. Keeping them separate prevents node updates from accidentally changing runtime policy.

## Related

- [[Graph State]]
- [[Graph State Persistence]]
