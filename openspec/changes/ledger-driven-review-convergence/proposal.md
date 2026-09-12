# Change: ledger-driven-review-convergence

**Series**: multi-vendor review robustness (phase 2 of 3)
**Depends on**: `harden-review-dispatch-parse-and-timeouts`
**Unlocks**: `pack-and-parallelize-vendor-review` (smaller packets), gate-time slice of `ambient-review-ledger`

## Why

Even when a vendor panel returns valid JSON, the review→fix loop does not
converge. It re-reviews the whole artifact every round, treats unconfirmed
medium findings as blocking, aborts on the first disagreement, and hands every
blocking finding to a fix agent with no file scope. Fixes then create new
surfaces that the next cold review attacks.

Evidence from this repo:

- `derive-descriptors-from-contracts` accumulated **nine** review round
  directories. The session log records four blocking findings across three
  rounds that were the same shape: a rename whose meaning depended on which
  wave had run.
- `add-agy-grok-pi-harnesses` round 2 found that round-1 PLAN_FIX-inserted
  tasks fell outside every package's stated task range — the repair work was
  the work most likely to be dropped.
- `converge()` prompt says "focus on remaining issues" but does not attach
  previous findings, their ids, or the files the last fix touched. Matching is
  Jaccard + path overlap at 0.6, with a fresh integer `id` per vendor per
  round. Plan reviews often have no `file_path`, so the same issue is
  **unconfirmed** rather than closed.
- `_is_blocking` treats medium+ confirmed *or unconfirmed* as blocking until
  the final round. The integration-gate spec already says unconfirmed findings
  warn only; the loop contradicts it.
- Disagreement returns `reason="disagreement"` and stops the loop, even when
  ten other findings are agreed and fixable. `rescope-review-convergence-disagreement-routing`
  already names this; this change implements the operational core without
  waiting on ri-06 recall numbers.
- Autopilot nests three caps: inner `max_rounds=3`, outer `PLAN_REVIEW` ↔
  `PLAN_FIX`, iterate-on-* max iterations. A "round" in session logs is a
  fresh multi-vendor review, not a re-check.

`ambient-review-ledger` designed a finding lifecycle (`open → addressed →
retired`) plus `compact`. That proposal is the git-hook / continuous sensor.
This change takes **only the gate-time slice**: a ledger the convergence loop
reads and writes, compact before a new hunt, delta review, tighter blocking,
parked disagreement, scoped fixes, one loop.

## What Changes

- A gate-time finding ledger under
  `openspec/changes/<id>/.review-ledger/` with `open / addressed / retired`
  lifecycle and stable ids (axis + normalized path + fingerprint). Not a
  post-commit hook.
- Round N>1 is **compact + delta**, not a cold review. Compact re-verifies
  open items against current `HEAD` and retires what is gone. The new hunt
  is the last-fix diff plus still-open items. Retired items are forbidden
  to re-litigate in the prompt.
- Blocking policy: a finding blocks the loop only if it is `deterministic`,
  **or** (`confirmed` ∧ criticality high/critical ∧ still `open` after
  compact). Unconfirmed medium never blocks. This aligns the loop with the
  existing integration-gate requirement "Unconfirmed Findings Warn Only."
- Disagreement is **parked** to a human queue file
  (`reviews/parked-disagreements.json`) and does **not** abort the loop.
  Agreed blocking items continue to fix. The integration gate may still
  surface parked items; it SHALL NOT treat "a disagreement existed" as
  `reason=disagreement` loop exit.
- Fix agents receive cited `file_path`s only, the finding text, and "do not
  add architecture, do not expand scope, do not edit specs unless type is
  `spec_gap`." One cluster per round (agreed blocking items), not the entire
  historical list. Post-fix runs Layer A (tests/linters/openspec validate)
  before another vendor panel.
- Autopilot `PLAN_FIX` / `IMPL_FIX` become the `fix_callback` *inside*
  `converge()`, not a second state machine that re-dispatches a cold review.
  One `max_rounds`, one stall rule (blocking count not decreasing after
  compact). **BREAKING** relative to the current `PLAN_REVIEW → PLAN_FIX →
  PLAN_REVIEW` outer bounce for the same findings.

Non-goals: git `post-commit` ambient review, GitHub-issue sync, kanban
swimlane, `refine-core` extraction (those remain `ambient-review-ledger`).
Non-goals: packed packets and parallel dispatch (phase 3).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Resilience | Blocking count after compact | Non-increasing across rounds on a seeded spiral fixture | Unit + fixture |
| Correctness | Unconfirmed medium findings | Do not enter `fix_callback` | Unit test |
| Correctness | Disagreement | Loop continues; parked file written; no `reason=disagreement` abort | Unit test |
| Compatibility | Ledger absent (phase 1 only checkout) | `converge()` still runs; compact is a no-op; warning logged | Unit test |
| Observability | Finding identity | Same defect keeps the same ledger id across two rounds | Unit test |
| Operability | Nested loop | A `PLAN_FIX` outcome does not dispatch a full cold review | Autopilot transition test |

## Approaches Considered

### Approach 1: Gate-time ledger, compact, delta, tighter blocking, park disagreement, collapse nested loops

Give findings identity. Re-verify before hunting. Review the delta. Block
only on deterministic or confirmed-high issues that compact still sees.
Park contested items. One engine.

- **Pros**: Directly kills the spiral; reuses review-findings + synthesizer
  matching; is the load-bearing slice of `ambient-review-ledger` without
  taking on git hooks; implements the spirit of
  `rescope-review-convergence-disagreement-routing` without waiting on ri-06.
- **Cons**: Touches autopilot phase transitions (breaking vs today's outer
  bounce); compact is another LLM or heuristic pass (this design uses
  heuristic re-verify first: path still exists + description tokens still in
  file; optional model compact later); ledger is a new on-disk format.
- **Effort**: M

### Approach 2: Raise the blocking threshold only

Change `_is_blocking` to high/critical confirmed, leave everything else.

- **Pros**: Tiny diff; immediately fewer fix rounds.
- **Cons**: Does not stop re-raising the same issue; does not stop
  fix-induced new findings; disagreement still aborts; nested loops remain.
- **Effort**: S

### Approach 3: Wait for full `ambient-review-ledger`

Do not build a gate-time ledger; implement the five-phase ambient proposal.

- **Pros**: One ledger for ambient and gates.
- **Cons**: Ambient is on-by-default per-commit LLM cost, a git hook, kanban,
  GitHub sync, and `refine-core` extraction. The spiral is a *gate* problem
  and does not need a post-commit sensor to start shrinking. Waiting blocks
  phase 3.
- **Effort**: L

### Recommended

**Approach 1.** Approach 2 is a subset (blocking policy) and is included, but
without identity and delta the next round still invents work. Approach 3 is
the right end state for continuous review, not the first patch for
convergence.

### Selected Approach

Approach 1. Selected by the operator on 2026-09-11 when requesting proposals
for all three phases. No modifications. Explicitly scoped as the gate-time
slice of `ambient-review-ledger`, not the git-hook half.

## Impact

- **Affected specs**: `skill-workflow` — MODIFIED Review Convergence Loop,
  Finding Trend Tracking and Stall Detection, Disagreement Classification /
  Disagreement Findings Escalate (loop exit), State Machine Phases (outer
  bounce), Fix Dispatch (scope + cluster). ADDED ledger, compact, delta
  review, parked disagreement, scoped fix cluster.
- **Affected code**:
  - `skills/autopilot/scripts/convergence_loop.py`
  - `skills/autopilot/scripts/autopilot.py` (PLAN_FIX / IMPL_FIX edges)
  - `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
    (stable id / ledger match reuse)
  - new `skills/parallel-infrastructure/scripts/review_ledger.py`
- **Related**: `ambient-review-ledger` (must consume this ledger later, not
  fork it); `rescope-review-convergence-disagreement-routing` (human-queue
  precision vs ri-06 remains that change's job; this change parks).
- **BREAKING**: `converge()` no longer returns `reason="disagreement"` as a
  hard stop. Autopilot no longer bounces `PLAN_REVIEW → PLAN_FIX →
  PLAN_REVIEW` as a second engine for the same findings.
