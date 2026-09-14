# Change: rescope-merge-pull-requests-to-plan-execute

## Why

`/merge-pull-requests` is still an operator console. The default path walks every
open PR through interactive Steps 3–11 (staleness, comments, vendor review,
holdout, merge/skip/close/address-comments). The 2026-08-24
`add-merge-plan-orchestration` change added a durable `merge-plan.json` and
`--execute --pr` kernel, but left interactive triage as the default and deferred
automated remediation. `execute_plan.py` never edits a PR branch; on unresolved
comments it only prints `/iterate-on-implementation` and `/quick-task`. It never
calls `/iterate-on-plan`. OpenSpec nodes halt at `proposal_acceptance` *before*
that hand-off, so the printed commands are unreachable for the PRs that need
them most.

The result is too many manual review steps for a pass that should look like
implementation: analyze merge order thoroughly (file overlap is not enough — the
2026-09-03 `#463` → `#464` `delegated_from` edge had to be inserted by hand),
discuss the plan with the operator, persist it, then work the DAG node by node
with the existing iterate + multi-vendor review loop until convergence, merge,
compact, next PR.

**Discovery (2026-09-10):** invert the default path; the orchestrator invokes
iterate skills (not halt-and-print); classify plan vs implementation with a
heuristic plus operator override; keep the cheap path for Dependabot / Jules /
Renovate when CI is green and comments are resolved. Agent context is compacted
after each merged node and re-seeded from `merge-plan.json`. Main-context
convergence stays once per pass.

## What Changes

- **BREAKING default path.** `/merge-pull-requests` analyzes the cohort, discusses
  merge order / kinds / deferrals / closes with the operator, persists
  `merge-plan.json` + `merge-plan.md`, then executes node-by-node. Today's
  per-PR action loop is retained as `--interactive` only.
- **Plan-only vs implementation kind.** Analysis classifies each OpenSpec node as
  `plan` (diff is only OpenSpec planning artifacts) or `implementation` (any
  other product/code/test files). The operator may override during the plan
  discussion. The artifact records `kind`, `change_id`, and
  `remediation_skill`.
- **Orchestrated remediation, not a printed seam.** For a `plan` node the
  conductor invokes `/iterate-on-plan <change-id> --vendor-review` in a managed
  worktree (iterate-on-plan requires an *unapproved* proposal — which is the
  merge-time state of a plan-only PR waiting on `proposal_acceptance`). For an
  `implementation` node it invokes `/iterate-on-implementation <change-id>
  --vendor-review` in a worktree (requires an *approved* proposal; halt if the
  PR is implementation and Gate 2 was never granted). Iterate skills own all
  branch edits. `execute_plan.py` still MUST NOT write PR code.
- **Multi-vendor review is iterate's exit, not a second console.** Coordinated
  iterate already dispatches `/parallel-review-plan` or
  `/parallel-review-implementation` and remediates consensus findings once.
  After that loop converges, execute-plan skips the duplicate PR-diff
  `vendor_review.py` pass for that node. Disagreement still routes to a human
  (align with `rescope-review-convergence-disagreement-routing`; unanimous
  agreement is not by itself a merge signal). `proposal_acceptance` remains a
  dedicated human gate that `--approve-gate` cannot release.
- **Cheap path for scoped automation.** Origin `dependabot` / `renovate` /
  `sentinel` / `bolt` / `palette` / `jules` with green CI and zero unresolved
  comments skip iterate and vendor review and merge with the existing origin
  strategy. Comments or failing CI drop them out of the cheap path.
- **Richer merge-order analysis.** `build_plan.py` still derives edges from file
  overlap and stacked bases, and the analysis round MUST also surface
  CI-failure class (transient / PR-specific / stale-base) and invite the
  operator to insert runtime prerequisite edges (the `#463`/`#464` case).
  `amend_plan()` stays the living-plan seam.
- **Per-node agent compact, once-per-pass repo convergence.** After a successful
  merge the conductor requests `/compact` (or equivalent fresh context) and
  resumes from the plan path + next ready PR. `merge-plan.json` is the resume
  artifact — do not overload autopilot `loop-state.json`. Step 11.6 main-context
  convergence remains exactly once per invocation that merged ≥1 PR.
- **Sync-point discipline around remediations.** Iterate worktrees are active
  agents. The merge kernel MUST NOT hold the exclusive main sync-point across
  iterate. It re-runs the active-agent guard after iterate finishes and before
  `refresh_branch` / merge. `--force` stays operator-only.
- Schema bump of `merge-plan.schema.json` (`1.0` → `1.1`) for `kind`,
  `change_id`, `remediation_skill`, and optional `inserted_reason` already
  present for runtime edges.

### Out of scope

- Coordinator-backed live plan storage (Phase 2 of 2026-08-24).
- New merge backends.
- Headless / unattended auto-merge (`add-headless-mode-to-merge-pull-requests`,
  always-on ri-12) — opposite control model.
- Rewriting `/iterate-on-plan` or `/iterate-on-implementation` internals beyond
  the invocation contract (always pass `--vendor-review` from this conductor).
- Splitting the oversized SKILL.md (`apply-progressive-disclosure-oversized-skills`)
  or rewiring script entry points (`add-self-describing-cli-entry-points`) —
  sequence those changes; do not absorb them.
- Changing autopilot. Autopilot never merges.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Operability | Default invocation without `--interactive` | Emits a validated plan, discusses it, then executes nodes; does not enter the per-PR action menu | Spec + skill-script tests |
| Compatibility | OpenSpec `proposal_acceptance` bypass via `--approve-gate` | 0 (gate remains, `override_allowed=false`) | Unit tests already in `test_execute_plan.py`, extended |
| Compatibility | `execute_plan` git checkout / commit / push on a PR branch | 0 occurrences | Grep gate + unit tests |
| Resilience | Eligible iterate review with no consensus, or vendor disagreement on a blocking finding | Node stays `pending`; merge is not invoked | Spec + execute/orchestrate tests |
| Operability | Cheap-path Dependabot/Jules node, CI green, 0 comments | Merged without iterate or vendor-review dispatch | `build_plan` + execute tests |
| Observability | After each successful node merge | Plan `outcome=merged`, downstream `needs_revalidation=true`, compact/resume pointer recorded | Plan-storage tests + skill contract |
| Compatibility | Main-context convergence count for a pass that merged k≥1 PRs | Exactly 1 | Existing convergence spec, unchanged |
| Resilience | Iterate worktree still registered when merge is attempted | Sync-point guard blocks; no auto-`--force` | Execute-plan sync-point tests |

## Approaches Considered

### Approach 1: SKILL.md conductor, execute_plan stays the merge kernel (Recommended)

Invert the skill's default path in `SKILL.md`. Add classification + schema fields
in `build_plan.py` / `merge-plan.schema.json`. Keep `execute_plan.py` as the
fail-closed merge/sync-point kernel (claim, refresh, security, `can_merge`,
OpenSpec gate, `merge_pr`). The conductor, between ready nodes, invokes the
existing iterate skills in worktrees, then calls `--execute --pr`, then
compacts. A small helper (classify kind, pick next ready node, record
remediation outcome) is allowed; the helper does not merge and does not edit
PR branches.

- **Pros:** Lands the deferred 2026-08-24 seam without copying iterate or
  autopilot. Preserves every merge safety invariant. Iterate already
  worktree-isolates and already has coordinated multi-vendor review. Matches
  how `/plan-feature` and `/implement-feature` already compose iterate.
- **Cons:** Two layers (conductor + kernel) to keep coherent. SKILL.md is
  already ~1070 lines; this rewrite grows the orchestration section (mitigate
  by not absorbing the progressive-disclosure split). Sync-point vs iterate
  worktree lifetime must be specified carefully.
- **Effort:** M

### Approach 2: DAG walker inside execute_plan.py

Extend `execute_plan.py` to walk the DAG, subprocess iterate skills, wait, then
merge, in one Python process. `--execute` without `--pr` means "run the plan."

- **Pros:** One entry point; plan mutations stay under the existing file-tier
  lock; easier to unit-test a state machine.
- **Cons:** Mixes a sync-point merge kernel with long-running worktree
  remediations that *are* active agents — the guard the kernel must pass would
  fire on its own children. Iterate is a skill (worktree, vendor CLIs, AskUser
  for assumptions), not a library. Turns `execute_plan.py` into a second
  autopilot. Harder to compact *agent* context between nodes because the
  process never yields.
- **Effort:** L

### Approach 3: Autopilot-style merge-loop-state.json

Introduce `docs/merge-logs/<pass>/loop-state.json` (or similar) with per-node
phases `REMEDIATE → REVIEW → MERGE → COMPACT`, reuse autopilot
`apply-outcome` / compact-hook `last_handoff_id` gating.

- **Pros:** Compact-between-nodes falls out of existing Stop-hook machinery.
  Familiar phase machine for anyone who knows autopilot.
- **Cons:** Autopilot's invariant is "never merges"; this skill's invariant is
  "is the merge sync-point." Overloading `loop-state.json` or the compact hook
  collides with `fix-compact-hook-phase-boundary-detection`. A third
  orchestrator (autopilot, autopilot-roadmap, merge-loop) for a problem the
  durable merge plan already solves as resume state.
- **Effort:** L

### Recommended

**Approach 1.** Discovery already chose invert-default, orchestrator-invokes-iterate,
heuristic+override, and cheap path. Approach 1 implements that shape by
*reusing* iterate and *not* expanding the merge kernel past merge safety.

Unselected (brief): Approach 2 (DAG walker inside `execute_plan.py`) fights the
sync-point guard because iterate worktrees are active agents. Approach 3
(autopilot-style merge `loop-state.json`) rebuilds a third orchestrator and
collides with compact-hook gating on autopilot `last_handoff_id`.

### Selected Approach

**Approach 1 — SKILL.md conductor, execute_plan stays the merge kernel.**

Selected at Gate 1 (2026-09-10). No modifications requested. Specs, tasks, and
design implement this approach only.

## Impact

- **Specs:** `merge-pull-requests` (MODIFIED — replace Interactive Merge
  Workflow as default; extend comment-addressing seam to `/iterate-on-plan`;
  add kind classification, conductor loop, compact-between-nodes).
  `skill-workflow` (MODIFIED — merge may invoke iterate skills as remediations;
  multi-vendor review is a required iterate exit when called from merge).
  `merge-infrastructure` (MODIFIED — plan schema 1.1 fields). `worktree`
  unchanged if remediations stay on feature branches.
- **Code:** `skills/merge-pull-requests/SKILL.md`,
  `contracts/merge-plan.schema.json`, `scripts/build_plan.py`,
  `scripts/merge_plan.py`, `scripts/execute_plan.py` (`_delegation_commands`
  grows `/iterate-on-plan`; still no branch edits), `scripts/render_plan.py`,
  tests under `scripts/tests/` and `skills/tests/merge-pull-requests/`. Optional
  thin `scripts/next_node.py` / kind classifier. Iterate SKILL.md only if the
  invocation contract needs an explicit "called-from-merge" note.
- **Sequencing:** do not land concurrently with
  `apply-progressive-disclosure-oversized-skills` or
  `add-self-describing-cli-entry-points` (same SKILL.md/scripts surface). Align
  vendor-disagreement routing with
  `rescope-review-convergence-disagreement-routing`.
- **Supersedes (partial):** the "out of scope" lines of archived
  `2026-08-24-add-merge-plan-orchestration` (automated comment-addressing, and
  replacing the interactive workflow as the default). Does not supersede Phase 2
  coordinator storage.
