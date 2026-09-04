---
type: Note
---

# LangGraph architecture questions

This collection captures the architecture questions and answers used to explain the LangGraph and DeepAgent design in this project.

## Questions

- [[Pipeline Topology]]
- [[Graph State]]
- [[Async Node Execution]]
- [[Reliability and Verification]]
- [[Bounded Agent Controller]]
- [[Graph State Persistence]]
- [[Settings and Run Controls]]
- [[DeepAgent Review Role]]
- [[DeepAgent Review Safety]]

## Key idea

The application is a deterministic LangGraph wiki compiler with optional, bounded agentic review. The normal pipeline is fixed and repeatable; DeepAgent work is opt-in, read-only, and advisory.
