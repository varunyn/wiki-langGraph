---
type: Note
wiki_langgraph_version: 1
wiki_langgraph_compiled: '2026-09-04T15:50:55Z'
modified: '2026-09-04T15:50:55Z'
created: '2026-09-04T15:50:55Z'
---
# LangGraph architecture questions

This collection captures the architecture questions and answers used to explain the LangGraph and DeepAgent design in this project.

## Questions

- [LangGraph Architecture/Pipeline Topology](Pipeline%20Topology.md)
- [LangGraph Architecture/Graph State](Graph%20State.md)
- [LangGraph Architecture/Async Node Execution](Async%20Node%20Execution.md)
- [LangGraph Architecture/Reliability and Verification](Reliability%20and%20Verification.md)
- [LangGraph Architecture/Bounded Agent Controller](Bounded%20Agent%20Controller.md)
- [LangGraph Architecture/Graph State Persistence](Graph%20State%20Persistence.md)
- [LangGraph Architecture/Settings and Run Controls](Settings%20and%20Run%20Controls.md)
- [LangGraph Architecture/DeepAgent Review Role](DeepAgent%20Review%20Role.md)
- [LangGraph Architecture/DeepAgent Review Safety](DeepAgent%20Review%20Safety.md)

## Key idea

The application is a deterministic LangGraph wiki compiler with optional, bounded agentic review. The normal pipeline is fixed and repeatable; DeepAgent work is opt-in, read-only, and advisory.