# Adjudicate single-vendor critical findings in both review gates

> Parent roadmap: `skill-rightsizing`
> Roadmap item: `ri-21`
> Change ID: `add-orchestrator-adjudication-review-gate`
> Effort: L
> Priority: 2

## Why

A high or critical judgment finding that no second vendor confirmed is treated as
advisory by the merge gate and escalated straight to a human by the convergence
loop. Neither outcome asks the one question that decides the case: is the claim
true?

PR #484 merged through an eligible two-vendor review with 23 findings, every one
`unconfirmed`, `blocking_count: 0` (`fixtures/pr484-consensus.json`). Four were
`high`. Two of those four were real spec defects and were fixed the next day in
#548 — an integer footer percent that contradicted `Coverage.percent`, and the
undefined phrase "nodes that export returns". Cross-vendor confirmation was
never going to catch them: the two vendors agreed on nothing at all
(`match_score: 0.0` on all 23), and two of the four dispatched vendors had
failed outright.

So confirmation is a poor proxy for correctness. Vendors phrase the same defect
differently (#478), vendors fail, and a lone reviewer is frequently right.
Operator direction is recorded on #550: such a finding must be **assessed for
correctness by the orchestrator** — not dropped as advisory, and not handed to a
human sight-unseen.

## What Changes

One shared predicate identifies unconfirmed high/critical judgment findings, and
both gates — the autopilot convergence loop and the merge-pull-requests
`execute_plan` vendor gate — route them to orchestrator adjudication instead of
passing or escalating them.

Adjudication produces one schema-validated verdict per finding: the claim is
`verified`, `refuted`, or `unverifiable`; `verified` and `refuted` require
`file:line` evidence; `impact_if_true` is `blocking` or `non_blocking`;
criticality is recalibrated; a justification is recorded. Each verdict is
stamped with the adjudicator's identity and the reviewed head SHA, and is stale
once the head moves.

Gate outcomes are then **computed in code** from the verdicts, never asserted by
the adjudicator:

| Verdict | Outcome |
|---|---|
| `verified` + `blocking` | block, with a fix hand-off |
| `unverifiable` + `blocking` | human queue (the existing escalation seam) |
| `refuted`, or any `non_blocking` | pass |

Only a claim the orchestrator could neither verify nor refute reaches a person.
That is the whole point: the orchestrator can read the code, so spending a human
on a claim it could have settled is waste, and dropping one it could have
confirmed is how #484 merged.

## Impact

- `review-convergence-safety` — the existing **High-impact judgment requires
  adjudication** requirement currently routes straight to escalation. It is
  modified so escalation becomes the residual path for `unverifiable` blocking
  claims only.
- `merge-pull-requests` — **Plan-Driven Single-PR Execution** blocks only on
  dispatch failure or an absent consensus verdict. It gains the adjudication
  gate, which is the #484 hole.
- Both gates share one predicate, so they cannot drift apart again.
- Escalation continues to use the existing supervise escalation seam. This
  change adds no new human queue.
- Two defects on `main` block this from working at all and are fixed here
  (see `design.md`): `ConsensusSynthesizer.to_dict()` drops `evidence_class`, so
  a persisted report cannot say which findings were judgment-class — verified
  against the #484 fixture, where the existing predicate selects **nothing** —
  and the predicate itself only accepts a ledger, which the merge path does not
  have.
- Draft PR #363 rewrites `consensus_synthesizer.py` heavily and adds its own
  adjudication *ledger* (`fixed | false_positive | accepted_risk`), which
  records what was decided about a blocker rather than whether a claim is true.
  To avoid a collision this change treats `ConsensusReport` as read-only and
  adds no field to `ConsensusFinding`. Whether #363 is revived or closed is an
  open operator decision that this change does not depend on.

## Non-Goals

- **Disagreement routing and precision measurement.** Contested-vs-agreed
  routing and measuring adjudication precision against a seeded-defect corpus
  belong to ri-16, which depends on this item and on ri-06.
- **Changing how consensus matches findings.** Wording-level match failure
  (#478) is real and is what makes this gate necessary, but improving the
  matcher is a separate change.
- **Replacing the escalation mechanism.** `unverifiable` blocking claims route
  to the existing seam as-is.

## Acceptance Outcomes

- Both gates use one shared predicate for unconfirmed high/critical judgment
  findings, and neither passes such a finding as advisory; each returns
  `adjudication_required`.
- Each verdict is schema-validated, carries `file:line` evidence for `verified`
  and `refuted`, and is stamped with adjudicator identity and the reviewed head
  SHA. A verdict whose head SHA is not the current head is stale and is not
  reused.
- Gate outcomes are computed in code from verdicts by the table above. Only
  `unverifiable` blocking claims reach a human.
- Adjudication performed by the same vendor family that authored the change
  under review is recorded and flagged in the gate result.
- Replaying `fixtures/pr484-consensus.json` yields exactly two `verified` +
  `blocking` verdicts, for findings 1 and 12 — the two defects #548 actually
  fixed — and neither 9 nor 11 blocks.

## Correction to the roadmap item

`ri-21` and issue #550 describe #484 as having "7 critical" unconfirmed
findings. The stored consensus does not support that: the 23 findings are 4
`high`, 12 `medium`, 7 `low`, and none are `critical`. The substance is
unchanged — four unconfirmed high findings, two of them real defects, zero
blocking — but the count is wrong and the replay fixture is built from the
stored data, not the claim. The roadmap item is corrected in the same pass.
