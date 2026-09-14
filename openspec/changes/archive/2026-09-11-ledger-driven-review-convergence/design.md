# Design: ledger-driven-review-convergence

## Context

`converge()` today:

```
for round in 1..max_rounds:
    prompt = build_review_prompt()          # no prior findings
    results = dispatch_and_wait(...)
    consensus = synthesize(...)
    if disagreement: return reason=disagreement
    blocking = medium+ confirmed|unconfirmed   # unconfirmed relaxed only on last round
    if not blocking: return converged
    if stall: return stalled
    fix_callback(all blocking)
```

Autopilot separately maps `PLAN_REVIEW not_converged → PLAN_FIX → PLAN_REVIEW`.
That outer bounce is a second engine over the same artifacts.

`ambient-review-ledger` proposed `.review-ledger/` plus `compact`. This change
owns the gate-time file format and the loop. The ambient proposal, when it
lands, SHALL read this ledger rather than invent a second one.

## Goals / Non-Goals

**Goals**

- Findings have identity across rounds.
- Rounds monotonically reduce open blocking items on a seeded spiral.
- Unconfirmed medium never fires a fix.
- Disagreement does not abort agreed work.
- One convergence engine.

**Non-goals**

- Post-commit hook, GitHub issue sync, kanban swimlane, `refine-core`.
- Packed review packets / parallel dispatch (phase 3).
- Measuring routing precision against ri-06 seeded defects (stays with
  `rescope-review-convergence-disagreement-routing`).
- Changing synthesizer match_score math except to emit a stable id.

## Decisions

### D1: Local-first ledger next to the change

Path: `openspec/changes/<change-id>/.review-ledger/ledger.json`. Schema
versioned. Entries: `{id, status, axis, type, criticality, evidence_class,
file_path, fingerprint, first_seen_round, last_seen_round, vendor_hits[],
description, resolution, parked_reason?}`. Status enum:
`open | addressed | retired | parked`.

Fingerprint = hash(canonical_axis + normalized_path + token-set of
description). New consensus findings merge into an existing id when
synthesizer `match_score` ≥ threshold **or** fingerprint matches. Otherwise
a new id is allocated (monotonic integer, not per-vendor `finding.id`).

### D2: Compact is heuristic first, model optional later

Compact for v1:

1. If `file_path` is set and the file no longer exists → `retired`.
2. If `file_path` is set and none of the description's significant tokens
   appear in the file (or in the line_range window ±20 lines) → `retired`.
3. If status was `addressed` (fix_callback claimed it) and compact still
   sees the tokens → back to `open` (fix did not take).
4. Otherwise leave `open`.

No extra LLM call in v1. A model compact is a follow-up; `ambient-review-ledger`
Phase 2 can replace the heuristic without changing the ledger schema.

### D3: Blocking set after compact

A ledger item is blocking iff:

- `status == open`, and
- `evidence_class == deterministic`, **or**
  (`consensus status == confirmed` ∧ criticality in `{high, critical}`)

Unconfirmed medium, nits, optional, fyi, none, and parked items never enter
`fix_callback`. This supersedes `_is_blocking`'s unconfirmed-medium rule and
the "relax unconfirmed only on the last round" special case (no longer
needed).

Phase 1's judgment ingest means CLI reviews are judgment; they block only
when confirmed high/critical and still open. Deterministic emitters still
block even unconfirmed (a failing test is enough).

### D4: Disagreement parks, loop continues

Matched findings with disagreeing dispositions get `status=parked` and are
appended to `openspec/changes/<id>/reviews/parked-disagreements.json`.
`converge()` does **not** return `reason="disagreement"`. If after parking
there are no blocking items, the loop has converged (with parked leftovers
surfaced in `ConvergenceResult.escalate_findings` as advisory). Autopilot
may still show parked items at the human merge gate.

The integration-gate requirement "Disagreement Findings Escalate" is
**modified**: disagreement escalates *as a parked human item*, not as a
loop abort. `BLOCKED_ESCALATE` at merge remains available when parked items
exist at SUBMIT_PR; it is not a mid-loop stop.

### D5: Delta prompt for round N>1

`build_review_prompt(round, ledger, last_fix_diff)`:

- Round 1: current behavior (plus phase 1 schema-derived contract) + "do not
  emit findings for issues already in the ledger" (empty on round 1).
- Round N>1: attach open ledger items, attach `git diff` of the last fix
  commit (or worktree dirty diff), instruct: re-verify open items; hunt only
  in the attached diff; do not re-open `retired` or `parked` items.

### D6: One engine — PLAN_FIX is fix_callback

`autopilot.py` transitions:

- `PLAN_REVIEW` `not_converged` no longer goes to a distinct `PLAN_FIX`
  phase that later re-enters `PLAN_REVIEW` as a cold review.
- `converge()` calls `fix_callback` internally (existing). Autopilot treats
  `converge()` as the whole PLAN_REVIEW phase. `PLAN_FIX` / `IMPL_FIX`
  remain phase names in `loop-state.json` for observability (a round's fix
  step) but are not outer-machine states that re-dispatch vendors.

If this is too sharp a break for resume compatibility, record
`PLAN_FIX` as a sub-step in `phase_history` without changing `current_phase`
away from `PLAN_REVIEW` until `converge()` returns.

Stall: after compact, if `len(blocking)` is not strictly less than the
previous round's post-compact blocking count, stall. Window of 2 is enough
because compact removes the "new invented findings" noise that forced a
window of 3.

### D7: Scoped fix cluster

`fix_callback` receives only current blocking items. Each item's allowed
paths = its `file_path` (and containing spec file if `type=spec_gap`).
Prompt forbids new architecture and out-of-scope files. Post-fix validator
(existing hook) runs; failures are attached and block the next vendor panel
until Layer A is green **or** the round budget is exhausted (then stall).

One cluster = all current blocking items that do not share a file, dispatched
in parallel as today; same-file items sequential. Do not send retired or
parked items.

### D8: Ledger is additive when missing

If `.review-ledger/` does not exist (phase 1-only checkout, or first round),
create it. No hard dependency that phase 1 code is present, but judgment
ingest from phase 1 is what makes D3 safe. The proposal depends on phase 1
landing first.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Blocking count non-increasing on spiral fixture | New fixture: round 1 invents extra medium unconfirmed; round 2 must not grow blocking | new |
| Unconfirmed medium never in fix_callback | Unit test on `_is_blocking` replacement | new |
| Disagreement does not abort | Unit test: disagreement + agreed blocking → fix_callback called, reason != disagreement | new |
| Missing ledger still runs | Unit test | new |
| Stable id across rounds | Unit test fingerprint merge | new |
| No outer cold re-review | Autopilot transition table test | new |

## Alternatives Considered

See proposal. Design-level reject: storing the ledger only in coordinator
memory. Gate-time review must work with coordinator down (existing
local-first posture).

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Heuristic compact retires a still-real finding | Tokens-in-file is conservative; missing file is the only auto-retire; addressed→open if tokens remain |
| Fingerprint misses paraphrases | Synthesizer match_score is the other merge path |
| Breaking autopilot resume of in-flight PLAN_FIX | D6 keeps PLAN_FIX as a phase_history sub-step; document resume of old loop-state as "finish current converge()" |
| Phase 1 not landed: judgment still default deterministic | Proposal depends on phase 1; if implemented out of order, confirmed-high still required so medium unconfirmed stop blocking anyway |
| Parked pile grows | Surface at SUBMIT_PR; human gate already exists |

## Migration Plan

New ledger files are gitignored or committed with the change (committed:
operators can see them in PRs; prefer **committed** under the change dir so
review artifacts stay with the proposal, same as `reviews/`). Old
`reason=disagreement` callers: `ConvergenceResult.reason` no longer uses
that value; map parked leftovers onto `escalate_findings`. Rollback: revert;
ledgers are inert files.
