# Design — add-autopilot-simplify-phase

## Context

`simplify-implementation` gained its prune gate, mock-aware assertion contract, and
phase-ordered workflow (characterize → prune → simplify) on this branch. The
`skill-workflow` spec still says the orchestrator SHALL NOT run it, a decision recorded on
2026-08-04 as operator preference plus a Rule 0.5 argument, with no exit criteria. This
change gives autopilot an opt-in `SIMPLIFY` phase and gives implementation review a
read-only `test_quality` finding type, and it names the measurables a default-on decision
will be judged on. Approach 1 (Gate 1): a first-class phase, an additive enum value.

## D1 — One dynamic target on two edges: `SIMPLIFY_OR_VALIDATE`

**Decision.** `TRANSITIONS["IMPL_REVIEW"]["converged"]` and the `--no-review` resolution of
`IMPL_REVIEW_OR_VALIDATE` (from `IMPL_ITERATE` `complete`) both become
`SIMPLIFY_OR_VALIDATE`. `transition()` resolves it: `"SIMPLIFY" if state.simplify_enabled
else "VALIDATE"`. `TRANSITIONS["SIMPLIFY"] = {"complete": "VALIDATE", "skipped": "VALIDATE",
"failed": "ESCALATE"}`.

**Why.** This is exactly how `VAL_REVIEW_OR_SUBMIT` gates the optional VAL_REVIEW phase
(`autopilot.py:199, 229-230`), so `test_phase_transitions.py`'s "single centralised table"
guard keeps holding. Resolving inside `transition()` rather than inside the two handlers
means the `--no-review` path cannot silently lose the phase — discovery decision 2.

**Rejected.** A `simplify_enabled` branch inside `_phase_impl_review` and
`_phase_impl_iterate`. Two call sites for one decision, and it moves routing out of the
table the tests guard.

## D2 — Soft outcomes; `skipped` never leaves a red head

**Decision.** Outcomes are `complete | skipped | failed`. Every refusal the skill can
produce (Rule of 500, unpinnable surface, `check_test_prune` exit 2, `check_test_contract`
exit 2, `verify_behavior_preservation` exit 2, nothing to do) maps to `skipped` with a
`skipped_reason` string. If any production edit exists when a refusal is raised, the phase
runs `git reset --hard <B1>` in its worktree before reporting. `failed` is reserved for the
dispatch itself throwing (adapter unavailable, worktree setup error) and goes to `ESCALATE`.

**Why.** The phase is polish. An opt-in polish step that escalates on "nothing to do" or
"too big to do by hand" would be worse than not having it. The reset guarantees VALIDATE
always sees either the pre-simplify head (`B1`) or a dual-run-proven head, never a partial
refactor. `B1` is the right reset point rather than `B0` because characterization and
prune commits are test-only, independently gated, and still valuable.

**Rejected.** Treating dual-run failure as `failed`. That would escalate a run whose
production code was never wrong — the simplification was.

## D3 — `LoopState` schema v6

**Decision.** Add `simplify_enabled: bool = False`, `simplify_baselines: dict | None =
None` (`{"b0": sha, "b1": sha}`), `simplify_report_path: str | None = None`. Bump
`LOOP_STATE_SCHEMA_VERSION` 5 → 6. `load_state` fills defaults for v5 files and rewrites
the version on next save, following the v3/v4/v5 precedent documented in the dataclass
docstring.

**Why baselines in state.** The dual-run is only meaningful against `B1`, the tip after
characterization and prune commits. On resume, recomputing `B1` from the current head is
wrong if any refactor commit already landed. Storing both SHAs makes resume reconstruct
the same comparison the un-interrupted run would have made.

## D4 — Dispatch shape: standard 3-step protocol, `implementer` archetype

**Decision.** SIMPLIFY uses `runner.py build-dispatch --phase SIMPLIFY` → adapter →
`runner.py apply-outcome`, like IMPL_ITERATE. `_PHASE_TASKS["SIMPLIFY"]` is a prompt that
invokes the `simplify-implementation` skill over `git diff <feature-base>...HEAD`, in the
phase worktree, and returns the outcome plus the evidence counters (D6). `archetypes.yaml`
maps SIMPLIFY → `implementer`; `_PHASE_SIGNAL_KEYS["SIMPLIFY"] = ["loc_estimate"]` so the
existing size-based escalation applies. `token_budget_check` gives SIMPLIFY the same budget
as IMPL_ITERATE and the same fallback model.

**Why.** No new dispatch concepts. The skill is the unit of behavior; the phase is a
thin, resumable wrapper that records outcome and evidence. `implementer` rather than
`architect` because the skill forbids design changes by construction.

## D5 — Artifact routing: explicit paths into the change directory

**Decision.** The phase passes `--report openspec/changes/<id>/simplify-report.json` and
uses `openspec/changes/<id>/test-prune-ledger.md` as the ledger path in every script
invocation. `simplify_report_path` in `LoopState` records the report location.

**Why.** `verify_behavior_preservation.py` defaults to a CWD-relative report, which is
right for manual use and wrong for an orchestrated phase that must leave evidence where
VALIDATE and the PR can find it. The scripts' defaults are left alone so manual
`/simplify-implementation` runs and external consumers are unaffected.

**Rejected.** Changing the script default to the change directory. That couples a
portable skill to this repo's OpenSpec layout.

## D6 — Evidence counters are the exit criteria the 2026-08-04 decision lacked

**Decision.** Every SIMPLIFY `phase_history` entry and `simplify-report.json` carry
`lines_removed`, `files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed`,
`skipped_reason`. Sources: `git diff --shortstat <B1>..HEAD` for the first two;
`check_test_prune.py --json` `removed_tests` length for `tests_pruned`;
`verify_behavior_preservation.py` exit code for `dual_run_passed`; `seams_removed` is
self-reported by the phase agent in its outcome payload (an integer ≥ 0, validated by
`apply-outcome`).

**Why.** A flag → measure → default-on path needs numbers, and `dual_run_passed=false`
frequency is the one that would keep the phase opt-in. `seams_removed` being self-reported
is a known weakness; a repo-wide reference-search diff is the mechanical replacement and is
out of scope here.

## D7 — `type: test_quality`, `criticality: low`, no new axis

**Decision.** Add `test_quality` to the `type` enum in the canonical review-findings
schema, its install mirror, `consensus-report.schema.json` (both copies), and
`vendor_review._FALLBACK_ENUMS`. Test-quality findings carry `axis: readability`
(source-mirroring, change-detector, duplicative, accessor-only, and all seam patterns) or
`axis: correctness` (self-mocking, vacuous). They are emitted at `criticality: low`.

**Why.** `_is_blocking` keys on `criticality` only, so `low` makes these findings visible
to the targeted fix path without ever blocking convergence on their own — the reviewer
flags, the implementer decides. `type` is the precedented, additive extension point
(`behavioral_failure`); `axis` participates in cross-vendor consensus matching and would
ripple into the synthesizer and both review skills' 8-axis prose. Discovery decision 1.

**Rejected.** A ninth axis; reusing `style` with a description prefix (unmeasurable later).

## D8 — Sequencing: implement after `fix-autopilot-archetype-and-apply-outcome` archives

**Decision.** Task 0.1 gates the implementation: confirm
`openspec/changes/archive/*-fix-autopilot-archetype-and-apply-outcome/` exists, rebase,
re-read `TRANSITIONS`, `LoopState`, and the `apply-outcome` contract, and adjust the Phase 1
anchors before writing code. Planning artifacts are written now against the current shape.

**Why.** That change is editing the same ~25 enumerations this one adds to, and is 54/59
tasks done. Adding SIMPLIFY once to the landed shape is one edit; adding it concurrently is
a rebase fight across every table. Discovery decision 3.

## D9 — Pre-existing drift is recorded, not fixed here

The following are adjacent to this change and deliberately untouched; each is a one-line
follow-up:

- `convergence-state.schema.json` phase enums omit `GATEKEEPER`, `PLAN_ITERATE`,
  `IMPL_ITERATE` and the v3–v5 `LoopState` fields. SIMPLIFY is added to the enum as-is.
- `spec.md` "Per-Phase Archetype Resolution" lists 7 dispatching phases while SKILL.md says
  8 (GATEKEEPER). This delta changes 7 → 8 by adding SIMPLIFY; the GATEKEEPER gap remains.
- `consensus-report.schema.json` `type` enum lacks `behavioral_failure`. This change adds
  `test_quality` to it and, since the identity test now covers this file, adds
  `behavioral_failure` too so the test can pass — the one drift item fixed here, because
  the new identity scenario cannot be satisfied otherwise.
- `parallel-review-implementation` Finding Types list omits `behavioral_failure`; the
  checklist edit in 2.4 adds both values to that list for the same reason.
- `spec.md:4339` "5-axis" wording.

## D10 — Two implementation packages with disjoint write scopes

`wp-autopilot-phase` owns `skills/autopilot/**`, the coordinator archetype config, and the
convergence-state schemas. `wp-review-diagnostic` owns the review-findings and
consensus-report schemas, `vendor_review.py`, and `parallel-review-implementation/SKILL.md`.
The single shared concern — a convergence test proving low-criticality `test_quality`
findings do not block — lives under `skills/tests/parallel-infrastructure/`, allocated to `wp-review-diagnostic`,
so the two write scopes share no path prefix. `wp-docs-and-mirrors` follows both and touches only
prose in other skills plus `docs/`; `wp-integration` closes.

## Task sizing

No task is L or XL. The two M-sized tasks (1.4 state machine + flag; 1.7 phase handler;
1.8 enumeration registration) are each a single outcome in one module group. Titles were
checked against the "and" heuristic; 1.8's "every enumeration" is one outcome (parity),
guarded by the structural test in 1.9.
