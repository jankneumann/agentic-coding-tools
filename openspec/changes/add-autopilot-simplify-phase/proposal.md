# Change: add-autopilot-simplify-phase

## Why

Agent-written code is systematically over-seamed: factory-of-one indirection, mock-only interfaces, and constructor parameters that exist only so a test could inject a double are the default shape of TDD-by-agent, and the freshly written tests that hold those seams open are cheapest to prune before anything fossilizes around them. The `simplify-implementation` skill now has the gates to do this safely (coverage gate, test-prune gate with ledger, mock-aware assertion contract, dual-run), but the `skill-workflow` spec still forbids the orchestrator from ever running it ("Manual invocation only", written on 2026-08-04 before those gates existed and recorded as operator preference with no exit criteria).

This change adds an **opt-in** `SIMPLIFY` phase to autopilot between implementation review and validation, and a **read-only** `test_quality` finding type to implementation review so that over-seamed tests are flagged in the review loop where findings already get fixed. It amends the manual-only requirement to "not default-on" and defines the measurables that a later default-on decision will be judged against. Default behavior is unchanged: without `--simplify`, autopilot's phase trace is byte-identical to today.

## What Changes

### `simplify-implementation`: two roles, one artifact

- The skill's workflow is restructured into a **Review role** (steps 0–4: scope, Chesterton's
  Fence, coverage-gate decision, candidate list, Rule of 500) that writes a
  **simplify review artifact**, and an **Apply role** (steps 5–8: characterize, prune, apply,
  dual-run, report) that consumes it. A manual run may perform both roles in one session but
  MUST write the artifact between them; autopilot dispatches them to different archetypes.
- The artifact is a review-findings document with `review_type: simplify`
  (`contracts/events/simplify-review.schema.json`). Each finding carries the catalog
  `pattern`, the fence verdict and evidence, the coverage decision, the consumer check for
  seams, and, for `test_quality` findings, the prune reason and `covered_by`.
- `test-prune-ledger.md` is **rendered from the artifact** by a new helper
  `scripts/simplify_review.py` (`validate` and `render-ledger` subcommands), so the ledger
  `check_test_prune.py` gates is the reviewer's decision, not the implementer's.
- The Apply role MUST NOT change a finding's fence verdict or disposition; a finding it
  cannot apply becomes `skipped` with a reason, and a verdict it disagrees with goes back
  to a human.

### Autopilot: two opt-in phases

- New `--simplify` flag, parsed like `--no-review` into `LoopState.simplify_enabled`
  (schema v5 → v6, with `simplify_baselines`, `simplify_review_path`,
  `simplify_report_path`; v5 files load at defaults).
- New phases `SIMPLIFY_REVIEW` (archetype `reviewer`, checkpoint-writing: may write only the
  artifact) and `SIMPLIFY_APPLY` (archetype `implementer`, write-capable). Slot: after
  `IMPL_REVIEW` converges **and** after `IMPL_ITERATE` completes under `--no-review`; both
  edges resolve through one dynamic target `SIMPLIFY_OR_VALIDATE`.
- `SIMPLIFY_REVIEW` outcomes: `findings` → `SIMPLIFY_APPLY`; `clean` (no applicable findings,
  Rule of 500 exceeded at review, or an artifact that fails validation, each with a recorded
  reason) → `VALIDATE`; `failed` (dispatch failure) → `ESCALATE`. When `IMPL_REVIEW` ran, its
  `test_quality` findings seed the review.
- `SIMPLIFY_APPLY` outcomes: `complete` → `VALIDATE`; `skipped` (unpinnable surface, prune
  gate, assertion contract, or dual-run exit 2, with the branch reset to the post-prune
  baseline `B1`) → `VALIDATE`; `failed` → `ESCALATE`. Commits land split
  (`test(...): pin`, `test(...): remove`, `refactor(...)`).
- Both phases are registered in every phase enumeration (`TRANSITIONS`, `transition()`,
  `_HANDOFF_BOUNDARIES`, `phase_agent` tables, `handoff_builder`, `token_budget_check`,
  `audit_log_validator`, `agents_config.WRITE_CAPABLE_PHASES` / `NON_TERMINAL_PHASES`,
  `archetypes.yaml`, both `convergence-state.schema.json` copies,
  `_PHASE_TO_REVIEW_TYPE`), guarded by a structural parity test. `goal_gate` is untouched.

### Implementation review: read-only `test_quality` findings

- `type` enum gains `test_quality` and `simplification`; `review_type` gains `simplify`
  (canonical schema, install mirror, both `consensus-report` copies, `vendor_review`
  fallback enums). `axis` is unchanged.
- `parallel-review-implementation` gains a **Test quality** checklist that flags new tests
  matching the Delete catalog and new test-induced seams as `test_quality` findings at
  `criticality: low`, which never block convergence on their own and are the seed for
  `SIMPLIFY_REVIEW`.

### Spec amendment

- "Simplify Skill Behavior-Preservation Contract": "operator-manual" becomes **not
  default-on**; `--simplify` is the operator request. "Manual invocation only" is replaced by
  "Not default-on" and "Flag is the operator request".
- Phase lists (14 → 15 non-terminal; 7 → 9 dispatching), write-capable phases, "Optional
  Post-Implementation Simplify Polish", "Review Findings Schema Extension", and "Simplify
  Mechanical Helper Scripts" are MODIFIED accordingly.
- ADDED: "Simplify Skill Review and Apply Roles", "Simplify Review Artifact",
  "Autopilot SIMPLIFY_REVIEW Phase", "Autopilot SIMPLIFY_APPLY Phase", "Autopilot SIMPLIFY
  Evidence", "Implementation Review Test-Quality Findings".

### Dependencies and sequencing

- **Depends on** `fix-autopilot-archetype-and-apply-outcome` archiving before
  `wp-autopilot-phases` starts (task 0.1). `wp-contracts`, `wp-simplify-skill`, and
  `wp-review-diagnostic` do not wait.
- **Adjacent, not blocking:** `ambient-review-ledger`, `factory-missions-architecture-alignment`
  (findings schema); the enum additions are additive and rebase cleanly.
- Pre-existing drift recorded in `design.md` D9, not fixed here, except where the new
  identity scenario cannot otherwise hold.

Nothing here is **BREAKING**: the flag is opt-in, every schema change is additive, v5
loop-state files load unchanged, and a manual `/simplify-implementation` run that performs
both roles behaves as before plus one artifact write.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | Autopilot phase trace with `--simplify` absent vs pre-change trace | Byte-identical phases and outcomes | Unit: `test_phase_transitions.py`; CI |
| Compatibility | Schema-v5 `loop-state.json` loaded by v6 `load_state` | Loads; new fields at defaults; no other field changed | Unit: loop-state migration test |
| Compatibility | `simplify-review.json` validates against both the contract and the canonical review-findings schema | Valid fixture passes both; invalid fixture rejected by the conditional rule | Unit: contract schema test (`wp-contracts`) |
| Compatibility | `type` / `review_type` enum identity across canonical, mirror, consensus-report, `_FALLBACK_ENUMS` | Identical; `simplify`, `simplification`, `test_quality` present | Unit: schema identity tests |
| Resilience | Review-role refusals and Apply-role refusals | 100% resolve to `clean` / `skipped` → `VALIDATE`; 0 leave HEAD ≠ `B1` after an Apply refusal | Unit: phase outcome tests |
| Resilience | Apply role cannot alter reviewer verdicts | `render-ledger` output equals the artifact's `prune` fields; a verdict change in Apply is a contract-test failure | Unit: `simplify_review.py` tests |
| Observability | SIMPLIFY `phase_history` entries and `simplify-report.json` | Every run records `findings_reviewed`, `findings_applied`, `findings_kept`, `lines_removed`, `files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed`, `skipped_reason` | Unit: report-shape test; VALIDATE evidence-completeness |
| Performance | Token budgets in `token_budget_check` | `SIMPLIFY_REVIEW` ≤ `IMPL_REVIEW`; `SIMPLIFY_APPLY` ≤ `IMPL_ITERATE` | CI token-budget job |

## Approaches Considered

### Approach 1: First-class opt-in phase plus additive finding type (Recommended)

`SIMPLIFY` becomes a real state-machine phase with its own dispatch, archetype, handoff boundary, token budget, and outcome record, slotted after review and before validation. The review-side diagnostic is a new `type` enum value, the lightest precedented schema extension.

- **Pros:** SIMPLIFY gets the same isolation, resume, escalation, and evidence machinery as every other phase; VALIDATE runs on the simplified head so the full validation suite is the second proof after the dual-run; `--no-review` runs still get the phase; the finding type is additive and rebases cleanly against the schema-reshaping changes; default trace unchanged.
- **Cons:** touches every phase enumeration (about 25 sites across autopilot scripts, coordinator config, schemas, docs, tests); must wait for `fix-autopilot-archetype-and-apply-outcome` to archive; adds a dispatch to opt-in runs.
- **Effort:** L as one package; split into two M packages (autopilot zone; review-skill + schema zone) with disjoint scopes.

### Approach 2: Trailing sub-step inside `IMPL_ITERATE`

When `--simplify` is set, `IMPL_ITERATE` runs `simplify-implementation` as its last step before reporting `complete`. No new phase, no enumeration edits, no dependency on the state-machine rewrite.

- **Pros:** smallest diff; ships now; no `loop-state` schema bump.
- **Cons:** conflates behavior-changing iteration with behavior-preserving refactor inside one phase outcome, which is the exact `fix`+`refactor` mixing the simplify contract forbids; runs *before* `IMPL_REVIEW`, so review-round targeted fixes re-introduce seams with no second pass; no per-phase archetype routing, token accounting, or handoff for the simplify work; a dual-run failure has no clean outcome to report other than failing IMPL_ITERATE.
- **Effort:** S.

### Approach 3: Post-validation polish phase

`SIMPLIFY` runs after `VALIDATE` passes and before `SUBMIT_PR`, on code that has already been fully validated.

- **Pros:** simplify never delays validation feedback; operates on the most stable head.
- **Cons:** the final head is then verified only by simplify's dual-run, not by VALIDATE; `goal_gate` binds DONE to the latest VALIDATE record and requires it to postdate the validation report, so post-VALIDATE commits either break the gate or force a second VALIDATE (doubling the most expensive phase); VAL_REVIEW would review a head that no longer exists.
- **Effort:** M, but unsafe under the current DONE gate.

**Recommendation: Approach 1.** Approach 2 saves effort by giving up the one property that made the manual-only decision reversible (split commits, separate outcome, second verification by VALIDATE). Approach 3 fails the existing DONE gate. Approach 1's cost is enumeration churn, and the decision to depend on the in-flight state-machine rewrite turns that churn into a single, well-timed edit rather than a rebase fight.

### Selected Approach

**Approach 1 — first-class opt-in phase plus additive finding type** (Gate 1, 2026-09-04),
**refined at Gate 2** into two roles with a review artifact between them:

- The single `SIMPLIFY` phase became `SIMPLIFY_REVIEW` (archetype `reviewer`,
  checkpoint-writing) → `SIMPLIFY_APPLY` (archetype `implementer`), mirroring
  `IMPL_REVIEW` / `IMPL_FIX`.
- The review artifact reuses the review-findings schema (`review_type: simplify`) and is the
  source the prune ledger is rendered from; `IMPL_REVIEW`'s `test_quality` findings seed it.
- The `simplify-implementation` skill itself is restructured into the same Review / Apply
  roles so the manual path and the orchestrated path share one contract.

Discovery decisions retained from Gate 1: `type: test_quality` at `criticality: low`
(no new axis); `--no-review` runs still get the phases; the autopilot package depends on
`fix-autopilot-archetype-and-apply-outcome` archiving; both halves ship in this change.

Approaches 2 and 3 remain rejected for the reasons above.

## Impact

**Affected specs (delta files):**
- `specs/skill-workflow/spec.md` — MODIFIED: State Machine Phases; Per-Phase Archetype
  Resolution in Autopilot; Autopilot Write-Capable Phases Use Worktree Isolation; Simplify
  Skill Behavior-Preservation Contract; Optional Post-Implementation Simplify Polish; Review
  Findings Schema Extension; Simplify Mechanical Helper Scripts. ADDED: Simplify Skill
  Review and Apply Roles; Simplify Review Artifact; Autopilot SIMPLIFY_REVIEW Phase;
  Autopilot SIMPLIFY_APPLY Phase; Autopilot SIMPLIFY Evidence; Implementation Review
  Test-Quality Findings.

**Affected code:**
- `skills/simplify-implementation/SKILL.md`, new `scripts/simplify_review.py`, tests
- `skills/autopilot/SKILL.md`, `scripts/autopilot.py`, `scripts/phase_agent.py`,
  `scripts/handoff_builder.py`, `scripts/token_budget_check.py`,
  `scripts/audit_log_validator.py`, `install_assets/openspec/schemas/convergence-state.schema.json`
- `agent-coordinator/src/agents_config.py`, `agent-coordinator/archetypes.yaml`
- `openspec/schemas/{convergence-state,review-findings,consensus-report}.schema.json` and
  their `skills/parallel-infrastructure/install_assets/` mirrors
- `skills/merge-pull-requests/scripts/vendor_review.py` (`_FALLBACK_ENUMS`)
- `skills/parallel-review-implementation/SKILL.md`
- `skills/implement-feature/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`
- `docs/autopilot-phase-archetype-resolution.md`, `docs/skill-flow/README.md`,
  `docs/skills-catalogue.md`, `docs/guides/testing-policy.md` (roles paragraph)
- Tests: `skills/tests/autopilot/*` phase fixtures, `skills/tests/simplify-implementation/*`,
  `skills/tests/parallel-infrastructure/*`, `skills/tests/merge-pull-requests/*`,
  `skills/tests/parallel-review-implementation/*`, `skills/validate-feature/scripts/tests/test_linters.py`

**Architecture layers:** Execution (dispatch, phase agent, skill scripts), Coordination
(loop-state, handoffs, archetype config, review artifact), Governance (spec amendment,
evidence contract). Trust layer untouched.
