# Add hypothesis-fact matrix and root-cause gate to validator

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-hypothesis-fact-matrix-and-root-cause-gate-to-validator`
> Effort: M
> Priority: 1

## Summary

Extend the ledger validator to compute the hypothesis-by-fact matrix (consistent / contradicted / unknown), per-fact column counts as signal strength, and all-consistent survivor rows. Reject any root_cause that cites no facts, is contradicted by a fact, or is a multi-cause hypothesis containing a non-necessary component.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- The validator rejects fixtures with an uncited root cause and with a root cause contradicted by a recorded fact.
- The validator emits the matrix with per-signal hypothesis counts and flags the all-consistent rows.
- The necessity check fails a combined hypothesis when removing one component leaves no fact unexplained.

## Rationale

The constraint that no root cause may be reported without fact citations needs a deterministic enforcement point, and the matrix is the ranking mechanism the rewritten debugging method and eliminative reviewer both rely on.
