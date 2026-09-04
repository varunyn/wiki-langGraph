---
type: Note
---

# How are failures and quality checks made visible?

If a graph node fails, its error handler adds a named failure message to the step log and sets `last_error`. The final lint node reports issue, warning, and error counts. A normal run exits with failure when the final state contains an error.

The bounded agent controller also reads this final state. It stops for human review when verification fails or warnings remain without a safe automatic fix.

## Why this design

A knowledge-base compiler should make partial success visible. Centralized final state gives the CLI and the bounded controller the same evidence for deciding whether the run was successful.

## Related

- [[Graph State]]
- [[Bounded Agent Controller]]
