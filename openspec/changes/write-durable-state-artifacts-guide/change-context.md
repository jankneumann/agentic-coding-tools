# Change Context: write-durable-state-artifacts-guide

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Test(s) | Contract Ref | Evidence |
|---|---|---|---|---|---|
| skill-workflow.state-artifacts-inventory | `specs/skill-workflow/spec.md` | Five artifact classes expose path, holder, writer, authority, consumers, and missing/stale behavior. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |
| skill-workflow.state-artifacts-authority | `specs/skill-workflow/spec.md` | Canonical loop/checkpoint state wins conflicts with advisory records or projections. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |
| skill-workflow.state-artifacts-rehydration | `specs/skill-workflow/spec.md` | Bootstrap discovery is separated from ordered canonical verification. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |
| skill-workflow.state-artifacts-missing | `specs/skill-workflow/spec.md` | Missing canonical state degrades rather than reconstructing truth. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |
| skill-workflow.state-artifacts-links | `specs/skill-workflow/spec.md` | Relevant skill sources link to the guide and supervise follows its order. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |
| skill-workflow.state-artifacts-mirrors | `specs/skill-workflow/spec.md` | Changed runtime mirrors are byte-identical. | `skills/tests/state-artifacts/` | `contracts/README.md` | pending |

## Coverage Summary

- Requirements traced: 6
- Tests mapped: 6 (planned RED/GREEN structural suite)
- Evidence collected: 0
- Gaps: implementation and validation pending
- Deferred: none

