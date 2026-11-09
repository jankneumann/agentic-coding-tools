# File consumer-driven contract tests upstream

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `consumer-contract-tests`
> Effort: L
> Priority: 3

## Summary

When /plan-feature plans a change that consumes another change's contract, write the consumer's needs as executable contract tests and propose them to the upstream change via PR to its owner; upstream /validate-feature runs them, and a spec-split helper partitions requirements into consumer-tested kernel and ranked backlog.

## Dependencies

- `ri-11`
- `ri-12`

## Acceptance Outcomes

- A consuming change's plan produces contract tests attributed to the consumer and proposed to the upstream change's owner.
- Upstream /validate-feature reports per-consumer contract test results.
- A spec-split helper partitions a capability's requirements into kernel (consumer-tested) and backlog (untested), preserving backlog rationale.

## Rationale

Concerns must be executable (P5) and dependents bind to contracts (P4); consumer tests define what the contract kernel must satisfy and supply the tests that reconciliation later unions.
