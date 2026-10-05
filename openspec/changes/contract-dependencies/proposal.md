# Bind roadmap dependencies to contracts

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `contract-dependencies`
> Effort: L
> Priority: 2

## Summary

Extend the roadmap schema so depends_on entries may bind to a dependency's contract ({item, on: contract}), add a contract_complete item state, teach /autopilot-roadmap, /supervise, and the queue projection to make dependents ready at contract-complete, and have /implement-feature generate stubs or fakes from the contract for unimplemented dependencies.

## Dependencies

- `ri-05`
- `ri-08`

## Acceptance Outcomes

- A roadmap item depending on a contract becomes a ready queue entry when its dependency reaches contract_complete, before that dependency is implemented.
- Existing bare depends_on entries keep implementation-complete semantics, and all existing roadmaps validate unchanged against the extended schema.
- /implement-feature provides a contract-generated stub for each contract dependency that is not yet implemented.
- contract_complete is recorded in roadmap.yaml / loop-state.json, so a rebuilt queue reproduces the same readiness.
- The memory-store simulation scenario shows reduced time-blocked-on-dependency compared with its baseline.

## Rationale

P4 says dependents should unblock at the agreed contract rather than wait for implementation; this removes the critical-path stall from the motivating incident.
