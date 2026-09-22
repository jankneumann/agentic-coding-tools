# Design: Adjudicate single-vendor critical findings in both review gates

## Context

Two gates consume multi-vendor review output and reach opposite conclusions
about the same class of finding.

**The convergence loop** (`skills/autopilot/scripts/convergence_loop.py:985-1036`)
calls `review_ledger.adjudication_items(ledger)` and, if it returns anything,
stops with `reason="adjudication_required"`, fires `escalation_callback`, and
does not invoke the fix callback. A human gets the finding, unexamined.

**The merge gate** (`skills/merge-pull-requests/scripts/execution_safety.py:37-76`,
called from `execute_plan.py:509-518`) reads one number:
`consensus["summary"]["blocking_count"]`. That number is computed at
`consensus_synthesizer.py:482-491`:

```python
blocking = sum(
    1
    for cf in consensus_findings
    if cf.evidence_class != JUDGMENT
    and (
        (cf.status == "confirmed" and cf.recommended_disposition == "fix")
        or cf.status == "disagreement"
    )
)
```

An `unconfirmed` finding can never reach that sum. Every single-vendor finding
is `unconfirmed` by construction — `_classify` assigns that status precisely
when no cross-vendor match exists. So the merge gate cannot block on a
single-vendor finding at any criticality. That is the #484 hole, and it is not
a bug in the arithmetic: nothing in the merge path ever asks whether the claim
is true.

## Two defects found while grounding this design

Both are on `main` today and both must be fixed for this change to function.

### DF1 — `evidence_class` is dropped when a consensus report is persisted

`ConsensusSynthesizer.to_dict()` (`consensus_synthesizer.py:657-685`) serializes
every `ConsensusFinding` field except `evidence_class`. The persisted report —
the artifact the merge gate stores as `vendor_verdict`, and the only record that
survives the run — therefore cannot distinguish a judgment finding from a
deterministic one.

Verified against the real #484 report (`fixtures/pr484-consensus.json`): 0 of 23
findings carry `evidence_class`. Feeding those findings straight into
`adjudication_items` selects **nothing**, because the predicate defaults a
missing `evidence_class` to `deterministic`:

```
predicate selects: []
```

`summary.advisory_count` is computed in memory from the same field, so the
report asserts "23 advisory" while making it impossible to say which 23. The
schema (`openspec/schemas/consensus-report.schema.json`) does not declare the
field either, though it sets no `additionalProperties: false`, so adding it is
backward compatible. `eligible_vendors` is serialized but likewise undeclared.

### DF2 — the predicate exists but only one gate can reach it

`review_ledger.adjudication_items()` (`review_ledger.py:511-530`) already
implements exactly the rule this change needs, and its field lookups already
tolerate consensus-shaped input (`item.get("criticality") or
item.get("agreed_criticality")`, `consensus_status or status`). But it takes a
**ledger**, and `skills/merge-pull-requests/` has no ledger and never imports it
— the merge gate operates on a single per-dispatch `ConsensusReport`.

So the asymmetry is not a disagreement about policy. One gate simply cannot see
the predicate the other one uses.

## Decisions

### D1 — Extract the item-level predicate; do not duplicate the rule

Split the loop body of `adjudication_items` into
`is_adjudication_candidate(item) -> bool` in `review_ledger.py`.
`adjudication_items(ledger)` keeps its signature and calls it. A new
`adjudication_candidates(findings)` applies it to any sequence of
finding-shaped dicts, which is what the merge gate has.

*Rejected:* a second copy of the rule in `merge-pull-requests`. Two copies of a
gate predicate is how the gates drifted apart in the first place.

### D2 — Fix DF1 rather than inferring judgment at the gate

The merge gate could treat a missing `evidence_class` as judgment. That would
make #484 block, and it would also reclassify every deterministic finding as
judgment, inverting `blocking_count` for confirmed findings.

Serialize the field instead, and declare it in the schema. Findings persisted
before this change have no `evidence_class`; the gate treats such a report as
**not adjudicable** and says so in the result, rather than guessing. A stale
report is a reason to re-review, not to invent evidence.

### D3 — Adjudication is a schema-constrained sub-agent verdict, one per finding

Each candidate is dispatched to an adjudicator with the finding, the diff, and
the code it names, under a rubric that requires a structured verdict. Per
finding rather than batched: verdicts stay independently attributable, evidence
cannot be smeared across claims, and the candidate set is small (four on #484).

The adjudicator returns judgment. It never returns a gate outcome — see D4.

*Rejected:* scoring findings by a deterministic heuristic. Whether "the spec
phrase is ambiguous" is true is not a function of a finding's fields; it is
answered by reading the spec.

### D4 — The gate outcome is computed in code, never asserted by the adjudicator

`gate_outcome(verdicts)` is a pure function:

| `claim` | `impact_if_true` | Outcome |
|---|---|---|
| `verified` | `blocking` | `block` — fix hand-off |
| `unverifiable` | `blocking` | `escalate` — human queue |
| `verified` | `non_blocking` | `pass` |
| `refuted` | any | `pass` |

An adjudicator that could return "pass" could also be persuaded to. Splitting
the judgment (is the claim true, and would it matter) from the consequence
(block, escalate, pass) keeps the second half auditable and testable without a
model in the loop.

### D5 — A verdict is bound to the head it reviewed

Each verdict carries `head_sha` and `adjudicator`. A verdict whose `head_sha` is
not the current head is stale and is not reused; the finding is re-adjudicated.
This mirrors the existing rule that iterate consensus is skipped only when its
`head_sha` matches the live PR head.

### D6 — Same-family adjudication is recorded and flagged, not forbidden

When the adjudicator's vendor family matches the family that authored the change
under review, the gate result carries `same_family: true`. Forbidding it would
make the gate unavailable in a single-vendor environment, which is the common
case here. Surfacing it lets a reviewer discount the verdict.

### D7 — Escalation reuses the existing seam

`unverifiable` + `blocking` routes to `escalation_callback` in the convergence
loop, unchanged, and to a fail-closed human gate in the merge path, consistent
with how `execute_plan` already handles `auto_executable: false`. No new human
queue. The supervise escalate-resume work in flight on
`openspec/recover-ri-06-escalation-routing` owns that seam's mechanics.

### D8 — Stay out of `consensus_synthesizer.py` internals (PR #363)

Draft PR #363 (`openspec/harden-review-consensus-and-recovery`, last updated
2026-08-11) rewrites `consensus_synthesizer.py` by +809/-150 and introduces its
own `consensus_policy.py` with an adjudication **ledger** whose vocabulary is
`fixed | false_positive | accepted_risk | unreviewed`. That vocabulary answers a
different question than this change: it records **what was decided about** a
blocker, whereas a verdict here records **whether the claim is true**. The two
can coexist, but editing the same dataclasses would collide badly.

This change therefore treats `ConsensusReport` as read-only and adds no field to
`ConsensusFinding`. The single exception is DF1, which adds one existing field
to the serializer — a change #363 must also make for its own ledger to be
usable, and a one-line addition either way.

*Open question for the operator:* whether #363 should be revived or closed. This
change does not depend on the answer.

## Components

| Component | Location | Responsibility |
|---|---|---|
| `is_adjudication_candidate` | `review_ledger.py` | The one predicate |
| `adjudication_candidates` | `review_ledger.py` | Apply it to consensus findings |
| `adjudicate()` | new `parallel-infrastructure/scripts/adjudication.py` | Dispatch one verdict per candidate |
| `gate_outcome()` | same | Pure verdict → outcome |
| verdict schema | `contracts/adjudication-verdict.schema.json` | Validate every verdict |
| merge gate wiring | `execution_safety.py`, `execute_plan.py` | Call the gate, persist verdicts |
| convergence wiring | `convergence_loop.py` | Adjudicate before escalating |

## Replay fixture

`fixtures/pr484-consensus.json` is the real stored report: 23 findings, all
`unconfirmed`, `blocking_count: 0`, `match_score: 0.0` throughout, from two
vendors (pi 15, antigravity 8) after two of four dispatched vendors failed.

Four findings are `high`; none are `critical`. Expected gate behavior once
`evidence_class` is present:

| Finding | Claim | Expected |
|---|---|---|
| 1 — footer format contradicts `Coverage.percent` | `verified` | `blocking` — fixed in #548 |
| 12 — "nodes that export returns" is undefined | `verified` | `blocking` — fixed in #548 |
| 9 — command injection via `--tree` target | — | must not block |
| 11 — work-package coupling / manual sync burden | — | must not block |

Findings 1 and 12 are precisely the two defects #548 shipped fixes for, which is
what makes this a golden test rather than a guess. The gate must return exactly
two blocking verdicts.

## Risks

- **The rubric is the product.** A vague rubric yields confident wrong verdicts,
  which is worse than today's silent drop because it launders a guess as a
  check. The #484 replay is the calibration: two specific findings verified, two
  specific findings not. ri-16 measures precision properly against ri-06's
  seeded-defect corpus.
- **Cost.** One dispatch per high/critical unconfirmed finding, on every
  eligible review. Bounded by the candidate count, which is small in practice,
  but it is not free and it is on the merge path.
- **Pre-`evidence_class` reports** cannot be adjudicated (D2). Until reviews
  re-run, the merge gate reports the report as not adjudicable rather than
  passing it silently.
