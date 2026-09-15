# Adjudicate single-vendor critical findings in both review gates

> Parent roadmap: `skill-rightsizing`
> Change ID: `add-orchestrator-adjudication-review-gate`
> Effort: L
> Priority: 2

## Summary

A high/critical judgment finding that no other vendor confirmed is neither advisory nor sent straight to a human. The autopilot convergence loop and the merge-pull-requests execute_plan gate share one predicate for such findings and return adjudication_required. The orchestrator verifies each against the code under a schema-constrained rubric, and code computes block, pass or human-gate from the verdicts.

## Dependencies

- None

## Acceptance Outcomes

- Both the autopilot convergence loop and the merge-pull-requests execute_plan gate use one shared predicate for unconfirmed high/critical judgment findings, and neither passes such a finding as advisory; each returns adjudication_required instead.
- The orchestrator records a schema-validated verdict per finding (claim verified, refuted or unverifiable; required file:line evidence for verified and refuted; impact_if_true blocking or non_blocking; calibrated criticality; justification), stamped with adjudicator identity and the reviewed head SHA. A verdict is stale once the head moves.
- Gate outcomes are computed in code from verdicts: verified plus blocking blocks with a fix hand-off, unverifiable plus blocking routes to the human queue, and refuted or non_blocking passes. Only unverifiable blocking claims reach a human.
- Adjudication performed by the same vendor family that authored the change is recorded and flagged in the gate result.
- A PR #484 replay fixture (7 single-vendor criticals) yields exactly the two verified blocking verdicts.

## Rationale

PR #484 merged through an eligible vendor review with 23 unconfirmed findings (7 critical) and blocking_count 0; two single-vendor criticals were real spec defects. Wording-level matching misses real agreement (#478) and vendors fail (2 of 4 on #484), so confirmation cannot be the only route to a block. Operator direction recorded on #550. No dependency: the gate protects merges now and is measured later by ri-16.
