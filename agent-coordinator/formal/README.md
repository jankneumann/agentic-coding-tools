# Coordination Formal Model

This folder contains bounded TLA+ model checks for core coordination invariants.

## Files

- `coordination.tla`: lock/task state machine model
- `coordination.cfg`: bounded constants + invariants/properties

## Run locally

```bash
./.github/scripts/run_tlc.sh
```

## Requirement mapping

- `Boundary Enforcement Integrity` -> modeled by the mutation transitions
- `Behavioral Assurance and Formal Verification`:
  - `Lock exclusivity invariant under concurrency` -> `LockExclusivity`
  - `Task claim uniqueness invariant` -> `TaskClaimUniqueness`
  - `Completion ownership invariant` -> `CompletionOwnership`
  - `Formal model safety check` -> TLC run of invariants/properties
