# Define durable executor authority boundary contract

> Parent roadmap: `durable-execution`
> Change ID: `define-durable-executor-authority-boundary-contract`
> Effort: M
> Priority: 3

## Summary

Define the authority boundary for a durable intra-phase executor in state-artifacts.md and phase_agent.py, with an adapter interface mapping engine run events onto phase progress checkpoints and engine tool-replay declarations onto effects-journal policies, and extend the AST guard so phase or package status is never read back from the executor ledger.

## Dependencies

- `ri-01`
- `ri-05`

## Acceptance Outcomes

- state-artifacts.md has an executor-ledger row whose authority is limited to intra-phase progress, and the rehydration order consults it only after loop-state.json identifies the phase.
- The AST guard in test_work_queue_projection_invariant.py (or a sibling) fails if phase or package status is read from the executor ledger.
- An engine tool declared non-replayable maps to a never_replay effect, verified by a unit test of the adapter mapping.
- With no executor configured, phase_agent.py behavior and outputs are identical to today's.

## Rationale

Phase 3; lets a durable engine plug in without creating a second source of truth, keeping loop-state.json authoritative for the phase and the effects journal for irreversible actions while opaque vendor CLIs stay first-class.
