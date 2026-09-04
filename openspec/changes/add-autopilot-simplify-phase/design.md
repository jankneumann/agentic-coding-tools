# Design — add-autopilot-simplify-phase

## Context

`simplify-implementation` gained its prune gate, mock-aware assertion contract, and
phase-ordered workflow on this branch. The `skill-workflow` spec still says the orchestrator
SHALL NOT run it — a 2026-08-04 decision recorded as operator preference plus a Rule 0.5
argument, with no exit criteria. Gate 1 chose a first-class opt-in phase. Gate 2 corrected
the shape: the skill is really **two roles** — a reviewer that produces an artifact and an
implementer that applies it — and the orchestrated path should dispatch them to different
archetypes with the artifact as the contract between them.

## D1 — Two phases, one dynamic target: `SIMPLIFY_OR_VALIDATE`

**Decision.** `TRANSITIONS["IMPL_REVIEW"]["converged"]` and the `--no-review` branch of
`IMPL_REVIEW_OR_VALIDATE` both become `SIMPLIFY_OR_VALIDATE`, resolved in `transition()` as
`"SIMPLIFY_REVIEW" if state.simplify_enabled else "VALIDATE"`. Then:

```
TRANSITIONS["SIMPLIFY_REVIEW"] = {"findings": "SIMPLIFY_APPLY", "clean": "VALIDATE", "failed": "ESCALATE"}
TRANSITIONS["SIMPLIFY_APPLY"]  = {"complete": "VALIDATE", "skipped": "VALIDATE", "failed": "ESCALATE"}
```

**Why.** Same mechanism as `VAL_REVIEW_OR_SUBMIT`, so the "single centralised table" guard in
`test_phase_transitions.py` keeps holding and the `--no-review` path cannot lose the phases.
Two phases rather than one with two internal dispatches (Gate 2 option) because each role
then has its own archetype resolution, handoff boundary, token budget, resume point, and
outcome record — an interruption between review and apply resumes at apply, with the
artifact already on disk.

**Rejected.** One `SIMPLIFY` phase with two dispatches (resume boundary hidden inside a
phase); branching inside the two upstream handlers (two call sites for one decision).

## D2 — The review artifact is a review-findings document

**Decision.** `SIMPLIFY_REVIEW` (and the manual Review role) writes
`openspec/changes/<id>/simplify-review.json`: a review-findings envelope with
`review_type: simplify`, `baseline_b0`, `scope`, and findings of `type: simplification |
test_quality`. Each finding carries `pattern` (catalog entry), `fence` (verdict, rationale,
evidence), `coverage` (pinned; behaviors to characterize), `consumer` (present / specified,
for seams), and for `test_quality` + `disposition: fix`, `prune` (reason, covered_by).
Contract: `contracts/events/simplify-review.schema.json`, composed by `allOf` over the
canonical schema.

**Why.** One schema family: the same `test_quality` finding that `IMPL_REVIEW` emits is what
`SIMPLIFY_REVIEW` refines, so `IMPL_REVIEW` output seeds the simplify review and both flow
through the existing checkpoint, consensus, and fix-callback machinery. The fence verdict,
coverage decision, and consumer check are exactly the judgments the skill's steps 1–4
already require; the artifact makes them reviewable instead of implicit.

**Conditional rules in the schema.** `disposition: fix` requires `fence.verdict: remove`;
`test_quality` + `fix` requires `prune` and `file_path`; `prune.reason` in the
coverage-required group requires a non-null `covered_by`. The invalid fixture exercises
the last rule.

**Rejected.** A bespoke `simplify-plan` format (second vocabulary for the same concept; no
seeding from `IMPL_REVIEW`).

## D3 — The prune ledger is rendered, not written

**Decision.** New `scripts/simplify_review.py` with `validate <artifact>` (contract +
canonical schema, exit 0/2/1) and `render-ledger <artifact> --out <path>` (emits
`test-prune-ledger.md` from every `test_quality` finding with `disposition: fix`, in the
exact format `check_test_prune.py` parses). The Apply role runs `render-ledger`, never
edits the ledger by hand, and `check_test_prune.py` gates it as before.

**Why.** The ledger is the reviewer's decision. Rendering it from the artifact means the
implementer cannot "justify" a deletion the reviewer did not make, and the existing prune
gate becomes a check that the implementer did what the reviewer said — which is the whole
point of splitting the roles. A round-trip test (artifact → ledger → `check_test_prune`
exit 0 on a synthetic repo) pins this.

## D4 — Role boundaries in the skill

**Decision.** `simplify-implementation/SKILL.md` gains a `## Roles` section. **Review**
(steps 0–4) is read-only with respect to code, may write only the artifact, and ends by
running `simplify_review.py validate`. **Apply** (steps 5–8) starts by validating the
artifact, MUST NOT change any finding's `fence.verdict` or `disposition`, characterizes
per `coverage.characterize`, renders the ledger, prunes, applies `simplification` findings
with `disposition: fix` one pattern at a time, dual-runs, and reports. A manual run may do
both roles in one session but must write the artifact between them. A finding the Apply
role cannot land becomes `skipped` with a reason in the report; a verdict it disagrees
with is raised to a human, not overwritten.

**Why.** Manual and orchestrated paths share one contract, so autopilot's phase prompts are
"run the Review role" / "run the Apply role" rather than a second description of the
workflow. The no-verdict-change rule is what keeps the reviewer's Chesterton's Fence
decisions load-bearing.

## D5 — Soft outcomes; refusals never leave a red head

**Decision.** `SIMPLIFY_REVIEW`: `findings` when at least one finding has
`disposition: fix`; `clean` otherwise, including Rule of 500 exceeded at review scope,
nothing to do, or an artifact that fails `validate` (reason recorded as
`skipped_reason: invalid_review_artifact` so a broken reviewer is visible, not silent);
`failed` only for dispatch failure. `SIMPLIFY_APPLY`: `skipped` with a reason for
unpinnable surface, `check_test_prune` / `check_test_contract` / dual-run exit 2, with
`git reset --hard <B1>` first if any production edit exists; `failed` only for dispatch
failure. Both `clean` and `skipped` transition to `VALIDATE`.

**Why.** Opt-in polish must not escalate a run whose production code was never wrong.
`B1` is the reset point because characterization and prune commits are test-only,
independently gated, and still valuable.

## D6 — `LoopState` schema v6

`simplify_enabled: bool = False`, `simplify_baselines: dict | None` (`{b0, b1}`),
`simplify_review_path: str | None`, `simplify_report_path: str | None`.
`LOOP_STATE_SCHEMA_VERSION` 5 → 6; v5 files load at defaults per the v3–v5 precedent.
Baselines and the artifact path are what make resume at `SIMPLIFY_APPLY` reconstruct the
same dual-run the uninterrupted run would have made.

## D7 — Archetypes, signals, budgets

`SIMPLIFY_REVIEW` → `reviewer`, signals `files_changed`, `lines_changed`, worktree
isolation "checkpoint-writing" like `IMPL_REVIEW` (writes only the artifact); budget ≤
`IMPL_REVIEW`. `SIMPLIFY_APPLY` → `implementer`, signals `findings_count`, `loc_estimate`,
write-capable; budget ≤ `IMPL_ITERATE`. `_PHASE_TO_REVIEW_TYPE["SIMPLIFY_REVIEW"] =
"simplify"`. Both use the standard 3-step dispatch protocol.

## D8 — Artifact routing and evidence

Explicit paths into the change directory: `simplify-review.json`,
`test-prune-ledger.md`, `simplify-report.json` (the script's CWD-relative default stays
for manual use). Evidence on every SIMPLIFY outcome, in `phase_history` and the report:
`findings_reviewed`, `findings_applied`, `findings_kept`, `lines_removed`,
`files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed`, `skipped_reason`.
The first three come from the artifact; the next four from `git diff --shortstat`,
`check_test_prune --json`, and the count of applied seam-pattern findings — so
`seams_removed` is no longer self-reported, which the Gate 1 plan had flagged as a
weakness. `dual_run_passed=false` frequency is the number that keeps the phases opt-in.

## D9 — `type: test_quality` / `simplification`, `review_type: simplify`, no new axis

Additive enum values in the canonical schema, install mirror, both `consensus-report`
copies, and `vendor_review._FALLBACK_ENUMS`. `criticality: low` on every simplify finding,
so `_is_blocking` (which keys on criticality) never blocks convergence on them. `axis` is
unchanged; `readability` for structure-coupled patterns, `correctness` for vacuous or
self-mocking tests, `architecture` for kept seams. `consensus-report` also gains
`behavioral_failure` where missing, because the new identity scenario covers that file.

## D10 — Sequencing and drift

`wp-autopilot-phases` starts only after `fix-autopilot-archetype-and-apply-outcome` is
archived (task 0.1); the other packages do not wait. Drift recorded, not fixed:
`convergence-state.schema.json` phase enums missing `GATEKEEPER`/`PLAN_ITERATE`/`IMPL_ITERATE`;
spec "7 dispatching phases" vs SKILL.md "8" (this delta says 9 by adding two, leaving the
GATEKEEPER gap); `parallel-review-implementation` Finding Types list missing
`behavioral_failure` (added alongside the new values in 4.2); `spec.md` "5-axis" wording.

## D11 — Packages

`wp-contracts` (root: artifact schema, fixtures, every enum edit) → in parallel
`wp-simplify-skill` (`skills/simplify-implementation/**`), `wp-autopilot-phases`
(`skills/autopilot/**`, coordinator archetype config, convergence-state schemas), and
`wp-review-diagnostic` (`parallel-review-implementation/SKILL.md`, its tests, one
convergence test under `skills/tests/parallel-infrastructure/`) → `wp-docs-and-mirrors`
→ `wp-integration`. Write scopes share no path prefix.

## Task sizing

No task is L or XL. The M-sized tasks (3.4 edge + state + flag; 3.9 apply handler; 3.10
enumeration registration; 2.4 skill restructure) are each one outcome in one module
group. Titles were checked against the "and" heuristic.
