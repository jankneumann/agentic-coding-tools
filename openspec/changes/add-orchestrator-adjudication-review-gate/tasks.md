# Tasks: Adjudicate single-vendor critical findings in both review gates

> Change ID: `add-orchestrator-adjudication-review-gate`
> Roadmap item: `ri-21` (`skill-rightsizing`)

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## wp-evidence-class — restore the field the gates depend on (DF1)

- [ ] 1.1 Serialize `evidence_class` in `ConsensusSynthesizer.to_dict()` (`consensus_synthesizer.py:657-685`). One key; do not touch matching, classification, or counting.
- [ ] 1.2 Declare `evidence_class` and the already-serialized `eligible_vendors` in `openspec/schemas/consensus-report.schema.json`.
- [ ] 1.3 Test: a report containing a judgment finding round-trips with `evidence_class` intact and validates against the schema.
- [ ] 1.4 Test: `summary.advisory_count` equals the number of serialized findings whose `evidence_class` is `judgment` — the invariant that silently failed before.

## wp-predicate — one predicate, two entry points (DF2, D1)

- [ ] 2.1 Extract the loop body of `review_ledger.adjudication_items()` into `is_adjudication_candidate(item)`; `adjudication_items(ledger)` delegates to it and keeps its signature.
- [ ] 2.2 Add `adjudication_candidates(findings)` for consensus-shaped input.
- [ ] 2.3 Test: the same #484 findings select identically through both entry points.
- [ ] 2.4 Test: exactly one definition of the predicate exists under `skills/` (AST guard, matching the existing `_get_ready_items` ownership test).
- [ ] 2.5 Test: a finding with no `evidence_class` is not selected, and is distinguishable from one explicitly marked `deterministic`.

## wp-verdict — the adjudication step (D3, D5, D6)

- [ ] 3.1 New `skills/parallel-infrastructure/scripts/adjudication.py` with `adjudicate(candidates, *, head_sha, context)`.
- [ ] 3.2 Author the rubric prompt: the finding, the diff, the code it names; a verdict per the contract; no gate outcome.
- [ ] 3.3 Validate every verdict against `contracts/adjudication-verdict.schema.json`; an invalid verdict leaves its finding unadjudicated rather than defaulting.
- [ ] 3.4 Stamp `adjudicator`, `head_sha`, and `same_family_as_author`.
- [ ] 3.5 Test: a `verified` verdict without `file:line` evidence is rejected.
- [ ] 3.6 Test: a verdict whose `head_sha` is not current is stale and triggers re-adjudication.
- [ ] 3.7 Test: adjudication dispatch failure fails closed — it never yields `pass`.

## wp-outcome — computed outcomes (D4)

- [ ] 4.1 `gate_outcome(verdicts)` in `adjudication.py`, a pure function over the D4 table.
- [ ] 4.2 Test the full cross product of `claim` × `impact_if_true`, including mixed verdict sets.
- [ ] 4.3 Test: an adjudicator payload naming a gate outcome has no effect on the computed outcome.

## wp-merge-gate — wire the merge path (D7)

- [ ] 5.1 Extend `vendor_review_block_reason` (`execution_safety.py:52-76`) so `blocking_count: 0` is no longer sufficient to pass.
- [ ] 5.2 Distinguish "not adjudicable" (no `evidence_class`) from "no blocking findings" in the reason string.
- [ ] 5.3 Persist verdicts into the node state next to `vendor_verdict`, and surface them through `_review_evidence` (`execute_plan.py:189-218`).
- [ ] 5.4 Route `unverifiable` + `blocking` to a fail-closed human gate, releasable only by `--approve-gate`.
- [ ] 5.5 Test: the #484 fixture, with `evidence_class` stamped, blocks the merge.

## wp-convergence — wire the autopilot path (D7)

- [ ] 6.1 Adjudicate at `convergence_loop.py:985-1036` before firing `escalation_callback`.
- [ ] 6.2 Pass only `unverifiable` + `blocking` claims to the escalation callback.
- [ ] 6.3 Hand `verified` + `blocking` claims to the fix path with their evidence.
- [ ] 6.4 Test: a verified blocking claim does not escalate; an unverifiable one does.
- [ ] 6.5 Test: medium-criticality judgment findings remain advisory (unchanged behavior).

## wp-replay — the golden test

- [ ] 7.1 Move `fixtures/pr484-consensus.json` into the canonical test tree.
- [ ] 7.2 Stub adjudicator verdicts from the recorded #548 outcome: findings 1 and 12 `verified` + `blocking`; 9 and 11 not blocking.
- [ ] 7.3 Test: the gate returns exactly two blocking verdicts, naming findings 1 and 12.
- [ ] 7.4 Test: the same fixture on today's `main` code path merges — the regression this change closes.

## wp-roadmap — corrections

- [ ] 8.1 Correct ri-21's rationale via `refine-roadmap`: #484 had 4 unconfirmed `high` findings (12 medium, 7 low), not "7 critical".
- [ ] 8.2 Correct the same count on issue #550 and in `docs/merge-logs/2026-09-14.md`.
