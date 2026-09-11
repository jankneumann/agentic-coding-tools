# Design: rescope-merge-pull-requests-to-plan-execute

## Context

Selected approach (Gate 1): invert `/merge-pull-requests` so the default path
is analyze → discuss → persist `merge-plan.json` → execute node-by-node.
`execute_plan.py` stays the fail-closed merge kernel. `/iterate-on-plan` and
`/iterate-on-implementation` (with `--vendor-review`) own PR-branch edits in
managed worktrees. Cheap path for Dependabot/Jules/Renovate/Sentinel/Bolt/Palette
when CI is green and comments are resolved.

This finishes two items archived `2026-08-24-add-merge-plan-orchestration`
explicitly deferred: replacing interactive triage as the default, and actually
running the iterate seam (then unsafe because Task agents ran on `main`; iterate
skills now worktree-isolate).

## Decisions

### D1 — Conductor in SKILL.md; kernel stays merge-only

The skill document is the DAG conductor (pick next ready node, invoke iterate,
request compact, call `--execute --pr`). `execute_plan.py` keeps claim, refresh,
security, `can_merge`, OpenSpec `proposal_acceptance`, and `merge_pr`. A thin
`next_node.py` helper may compute the next ready PR from the plan file; it
MUST NOT merge or edit branches.

- Rejected: DAG walker inside `execute_plan.py` (Approach 2) — iterate worktrees
  are active agents and would trip the kernel's own sync-point guard.
- Rejected: merge `loop-state.json` (Approach 3) — `merge-plan.json` is already
  the resume artifact; autopilot compact-hook keys off a different file.

### D2 — Kind heuristic is prefix-based, override is authoritative

`plan` iff every changed file is under `openspec/changes/<change-id>/`.
OpenSpec/codex/other diffs that escape that prefix are `implementation`.
Listed automation origins are `automation`. After the operator approves a
plan revision, persisted `kind` / `remediation_skill` win; execution MUST NOT
silently re-heuristic.

### D3 — Iterate's parallel-review is the review of record

Merge-triggered iterate always passes `--vendor-review`. After consensus HEAD
matches the live PR head, `--execute` skips `vendor_review.py` (PR-diff,
`review_type=pr`). Residual PR-diff review remains for nodes that never ran
iterate and are still eligible. Disagreement on a blocking finding is a human
halt. Unanimous agreement does not release `proposal_acceptance`.

Aligns with `rescope-review-convergence-disagreement-routing` without waiting
on that change: this conductor already treats disagreement as a halt.

### D4 — Cheap path is origin + live CI + zero comments

Origins: `dependabot`, `renovate`, `sentinel`, `bolt`, `palette`, `jules`.
Green CI and zero unresolved comments → merge with existing origin strategy,
no iterate, no vendor review. Any comment or failing check drops the node out.

### D5 — Compact agent context; one repo convergence per pass

After `outcome=merged`, request `/compact` and resume from the plan path + next
PR. Do not write autopilot `loop-state.json`. Step 11.6 main-context
convergence stays exactly once per invocation that merged ≥1 PR (unchanged
spec). Those are different layers: conversation tokens vs derived docs on `main`.

### D6 — Sync-point is not held across iterate

Iterate creates feature worktrees. Holding exclusive main access across that
would deadlock the guard the kernel must pass after iterate returns. Sequence:
release / never acquire → iterate → teardown or wait until the iterate
worktree is inactive → re-check `check_no_active_agents` → claim → refresh/merge.
Never auto-`--force`.

### D7 — Schema 1.1 is additive

Bump `schema_version` const from `"1.0"` to `"1.1"`. New definition fields:
`kind`, `change_id`, `remediation_skill`. New live fields: `ci_failure_class`,
optional compact/resume pointer at plan level. Existing 1.0 readers MUST fail
closed on version mismatch rather than drop the new fields.

### D8 — Mechanical DAG plus operator runtime edges

Keep file-overlap and stacked-base edges. Analysis also labels CI-failure class
(`transient` / `pr_specific` / `stale_base`) using the existing Step 5b rules
already in SKILL.md. Runtime prerequisites the overlap deriver cannot see
(2026-09-03 `#463` → `#464`) are operator-inserted via `amend_plan()` with
`inserted_reason` during the plan discussion, not guessed by the heuristic.

### D9 — Iterate preconditions are fail-closed

`iterate-on-plan` requires an unapproved proposal; `iterate-on-implementation`
requires an approved one. The conductor checks that before dispatch. Wrong
pairing → `pending` + blocking reason, no skill invocation.

## Task decomposition note

No XL tasks. The SKILL.md rewrite is split (default path, `--interactive`,
compact/sync-point prose) so none of those is L. The execute-kernel vendor-review
skip is a separate M from delegation routing.

## Risks

- SKILL.md size vs `apply-progressive-disclosure-oversized-skills`: do not
  split files in this change; sequence that rewrite after.
- `add-self-describing-cli-entry-points` rewires script invocation: keep
  canonical `skills/merge-pull-requests/scripts` paths.
- Headless auto-merge (ri-12) is the opposite control model; out of scope.
- Iterate assumption-AskUserQuestion during a merge pass: accept the halt;
  the plan file survives compact.
