---
type: Note
---

# Why is the bounded agent controller outside the main graph?

The main graph executes one deterministic compile pipeline. The optional `agent` command is a separate controller that inspects the corpus, manifest, and review queue; chooses a predefined safe action; runs the graph; verifies the result; and replans within a strict iteration limit.

It does not ask an LLM to invent shell commands or retry indefinitely. When it cannot identify a safe next action, it stops for review.

## Why this design

Keeping operational planning outside the compiler graph makes the core workflow easier to reason about, test, and run predictably. It adds bounded automation without making everyday compilation autonomous.

## Related

- [[Reliability and Verification]]
- [[DeepAgent Review Role]]
