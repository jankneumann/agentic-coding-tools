# Change: add-autopilot-simplify-phase

## Why

Agent-written code is systematically over-seamed: factory-of-one indirection, mock-only interfaces, and constructor parameters that exist only so a test could inject a double are the default shape of TDD-by-agent, and the freshly written tests that hold those seams open are cheapest to prune before anything fossilizes around them. The `simplify-implementation` skill now has the gates to do this safely (coverage gate, test-prune gate with ledger, mock-aware assertion contract, dual-run), but the `skill-workflow` spec still forbids the orchestrator from ever running it ("Manual invocation only", written on 2026-08-04 before those gates existed and recorded as operator preference with no exit criteria).

This change adds an **opt-in** `SIMPLIFY` phase to autopilot between implementation review and validation, and a **read-only** `test_quality` finding type to implementation review so that over-seamed tests are flagged in the review loop where findings already get fixed. It amends the manual-only requirement to "not default-on" and defines the measurables that a later default-on decision will be judged against. Default behavior is unchanged: without `--simplify`, autopilot's phase trace is byte-identical to today.

## What Changes

### Autopilot: opt-in `SIMPLIFY` phase

- New `--simplify` flag, parsed like `--no-review` (substring match on `$ARGUMENTS`) into `LoopState.simplify_enabled` (schema v5 → v6; v5 files load with `simplify_enabled=false`).
- New phase `SIMPLIFY`, write-capable, dispatched through the standard 3-step protocol (`build-dispatch` → adapter → `apply-outcome`). Slot: after `IMPL_REVIEW` converges, **and** after `IMPL_ITERATE` completes when `--no-review` skipped review. Both edges resolve through a new dynamic target `SIMPLIFY_OR_VALIDATE`, mirroring `VAL_REVIEW_OR_SUBMIT`.
- The phase runs `simplify-implementation` on the change's diff: characterize → prune → simplify → dual-run, per that skill's phase model. Baselines `B0`/`B1` and the report path are recorded in `loop-state.json` so the dual-run is reconstructible on resume.
- **Soft phase.** Outcomes are `complete`, `skipped`, `failed`. `skipped` (with a reason: Rule of 500 exceeded, surface unpinnable, nothing to do, prune gate blocked, dual-run failed) always transitions to `VALIDATE`. Only an infrastructure failure of the dispatch itself yields `failed` → `ESCALATE`. A dual-run failure reverts the simplify range and reports `skipped`; it never leaves a red head for VALIDATE.
- Commits land split: `test(<scope>): pin …`, `test(<scope>): remove …`, `refactor(<scope>): …`. The prune ledger, when any test is removed, is written to `openspec/changes/<change-id>/test-prune-ledger.md`; `simplify-report.json` is written to `openspec/changes/<change-id>/simplify-report.json` (explicit `--report`, since the script's default is CWD-relative).
- Phase enumerations updated together: `TRANSITIONS`, `transition()`, `_HANDOFF_BOUNDARIES`, `phase_agent` tables (`_WORKTREE_PHASES`, `_PHASE_SIGNAL_KEYS`, `_PHASE_TASKS`, expected outcomes), `handoff_builder` labels, `token_budget_check._DISPATCHING_PHASES` and fallback model, `audit_log_validator` phase-model table and canonical-trace synthesis, `agents_config.WRITE_CAPABLE_PHASES` / `NON_TERMINAL_PHASES`, `archetypes.yaml` `phase_mapping` (SIMPLIFY → `implementer` archetype), `convergence-state.schema.json` phase enums (canonical + install mirror).
- `goal_gate` is untouched: SIMPLIFY precedes VALIDATE, so DONE still binds to the latest VALIDATE record on the final head.

### Implementation review: read-only `test_quality` findings

- New value `test_quality` in the review-findings `type` enum (canonical schema, install mirror, `consensus-report.schema.json`, and the hand-copied `_FALLBACK_ENUMS` in `merge-pull-requests/scripts/vendor_review.py`), following the `behavioral_failure` precedent. `axis` stays 8-valued; test-quality findings carry `axis: readability` (change-detector, duplicative, source-mirroring) or `axis: correctness` (self-mocking, vacuous).
- `parallel-review-implementation` gains a "Test quality" checklist under Code Quality Review that flags new tests matching the `simplify-implementation` Delete catalog and new test-induced seams (factory-of-one, mock-only interface, test-only constructor parameter, `_for_testing` hook). Findings are emitted at `criticality: low` so they never block convergence by themselves; the targeted fix path may still act on them.
- No new axis, no synthesizer changes.

### Spec amendment

- `skill-workflow` › "Simplify Skill Behavior-Preservation Contract": the sentence "invocation SHALL remain operator-manual (not default-enabled in autopilot)" and the scenario "Manual invocation only" become **not default-on**: the orchestrator SHALL NOT run a simplify phase unless `--simplify` is passed, and the flag is an operator request.
- `skill-workflow` › autopilot phase list / dispatching-phase list / write-capable phases: add `SIMPLIFY` (opt-in).
- `skill-workflow` › "Optional Post-Implementation Simplify Polish": name the flag so `implement-feature` and `iterate-on-implementation` stop reading as forbidding the phase.
- `skill-workflow` › "Review Findings Schema Extension": add `test_quality` to the `type` enum scenario set.
- New requirement "Autopilot SIMPLIFY Phase Evidence": every SIMPLIFY run records, in `phase_history` and `simplify-report.json`, the counts that a default-on decision will be judged on (see Non-Functional Requirements).

### Dependencies and sequencing

- **Depends on** `fix-autopilot-archetype-and-apply-outcome` archiving first. That change is rewriting the same enumerations (54/59 tasks done). Implementation of this change starts against its landed shape; planning proceeds now.
- **Adjacent, not blocking:** `ambient-review-ledger` and `factory-missions-architecture-alignment` reshape the findings schema. Adding one `type` value is additive and rebases cleanly; if either lands first, re-run the schema-identity tests.
- Pre-existing drift this change is adjacent to but does **not** fix (filed as follow-ups in `design.md`): `convergence-state.schema.json` phase enums missing `GATEKEEPER`/`PLAN_ITERATE`/`IMPL_ITERATE`; spec line "7 dispatching phases" vs SKILL.md "8"; `consensus-report.schema.json` missing `behavioral_failure`; "5-axis" wording in one spec paragraph. The `SIMPLIFY` additions are made in a way that does not depend on those being fixed.

Nothing here is **BREAKING**: the flag is opt-in, the schema change is additive, and v5 loop-state files load unchanged.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | Autopilot phase trace with `--simplify` absent, diffed against pre-change trace | Byte-identical (`phase_history` phases and outcomes) | Unit: `skills/tests/autopilot/test_phase_transitions.py`; CI |
| Compatibility | Schema-v5 `loop-state.json` loaded by v6 `load_state` | Loads; `simplify_enabled == False`; no other field changed | Unit: loop-state migration test |
| Resilience | SIMPLIFY refusal paths (Rule of 500, unpinnable, prune gate exit 2, dual-run exit 2) | 100% resolve to outcome `skipped` → `VALIDATE`; 0 leave HEAD ≠ `B1` on dual-run failure | Unit: phase outcome tests with scripted refusals |
| Observability | SIMPLIFY `phase_history` entry and `simplify-report.json` | Every run records: `lines_removed`, `files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed`, `skipped_reason` | Unit: report-shape test; VALIDATE evidence-completeness check |
| Performance | Token budget for SIMPLIFY in `token_budget_check` | ≤ the `IMPL_ITERATE` budget; counted in the CI token-budget gate | CI token-budget job |
| Compatibility | Review-findings schema identity across canonical, install mirror, and `_FALLBACK_ENUMS` | Identical enums, `test_quality` present in all three | Unit: `test_review_findings_schema.py`, `test_vendor_review_prompt.py` |

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

**Approach 1 — first-class opt-in phase plus additive finding type** (Gate 1, 2026-09-04).
Discovery decisions recorded at the same gate:

- Finding representation: new `type: test_quality`, emitted at `criticality: low`; `axis` unchanged.
- `--no-review` runs still execute SIMPLIFY when `--simplify` is set (both edges intercepted).
- Sequencing: this change **depends on** `fix-autopilot-archetype-and-apply-outcome` archiving first; implementation starts against its landed state-machine shape.
- Scope: both the autopilot phase and the review-side diagnostic ship in this change, as two work packages with disjoint write scopes.

No modifications to the approach were requested. Approaches 2 and 3 are retained above as rejected alternatives.

## Impact

**Affected specs (delta files):**
- `specs/skill-workflow/spec.md` — MODIFIED: Simplify Skill Behavior-Preservation Contract (manual → not default-on); Autopilot phase list, dispatching phases, write-capable phases (add SIMPLIFY); Optional Post-Implementation Simplify Polish (name the flag); Review Findings Schema Extension (add `test_quality`). ADDED: Autopilot SIMPLIFY Phase; Autopilot SIMPLIFY Phase Evidence; Implementation Review Test-Quality Findings.

**Affected code:**
- `skills/autopilot/SKILL.md`, `scripts/autopilot.py`, `scripts/phase_agent.py`, `scripts/handoff_builder.py`, `scripts/token_budget_check.py`, `scripts/audit_log_validator.py`, `install_assets/openspec/schemas/convergence-state.schema.json`
- `agent-coordinator/src/agents_config.py`, `agent-coordinator/archetypes.yaml`
- `openspec/schemas/convergence-state.schema.json`, `openspec/schemas/review-findings.schema.json`, `openspec/schemas/consensus-report.schema.json` and their `skills/parallel-infrastructure/install_assets/` mirrors
- `skills/merge-pull-requests/scripts/vendor_review.py` (`_FALLBACK_ENUMS`)
- `skills/parallel-review-implementation/SKILL.md`
- `skills/simplify-implementation/SKILL.md` (invocation-mode wording: flag is the operator request), `skills/implement-feature/SKILL.md`, `skills/iterate-on-implementation/SKILL.md` (polish paragraphs name the flag)
- `docs/autopilot-phase-archetype-resolution.md`, `docs/skill-flow/README.md`, `docs/skills-catalogue.md`
- Tests: `skills/tests/autopilot/*` phase-list fixtures, `skills/tests/parallel-infrastructure/test_review_findings_schema.py`, `skills/tests/merge-pull-requests/test_vendor_review_prompt.py`, `skills/validate-feature/scripts/tests/test_linters.py`

**Architecture layers:** Execution (autopilot dispatch, phase agent), Coordination (loop-state, handoffs, archetype config), Governance (spec amendment, evidence contract). Trust layer untouched.
