# Validation Report: dispatch-contract

**Date**: 2026-10-10
**Commit**: c83cf40 (branch head on origin; re-validation, operator gate-decision 724eaee2, lease generation 5)
**Branch**: openspec/dispatch-contract (merged via PR #667 as 0d078ff)

This report was regenerated against the current head. It supersedes the 2026-10-09 report (VALIDATE at 7cc9180,
VAL_REVIEW at df3b98e). Code under test now includes the PR #667 review fixes (765f9d8 resume only the recorded
escalation subject's dispatches; b35e544 keep a repo-root harness isolation as the portable ref "."; 43a9b11
single-flight capability/permission park resolution; 6a0a096 records them), the post-merge fixes 4955e24
(digest-only launch tokens in the live checkpoint), c04a1a8 (accept an already-migrated live checkpoint),
789705a (verified isolation mode in the attempt profile), and the cherry-picked goal-gate fix f44bbd6 (goal gate binds
to the report's last writer and commit time, so VAL_REVIEW binds after VALIDATE) and resume-at-VALIDATE commits
(3a29785, c83cf40).

Scope: skills scripts, shared libraries, and JSON schemas only. There is no deployable
service (no docker-compose, agent-coordinator/, packages/ or apps/ path changed; the only
non-skills/openspec/docs path is the root `TRUST_POSTURE.template.md`). Container-dependent
phases are therefore not applicable, not skipped.

## Phase Results

- Deploy: not applicable (no deployable surface)
- Smoke: not applicable (no live service)
- Gen-Eval: not applicable (no descriptors touched; no service)
- Security: not applicable for live scanners (no service); secret scan evidence under Spec Compliance outcome 6
- E2E: not applicable (no browser-facing surface)
- Architecture: not run (advisory; no service/graph consumer touched)
- Task drift: pass (0 unchecked boxes in tasks.md)
- OpenSpec: pass (`openspec validate dispatch-contract --strict`: valid)
- Lint: pass (`ruff check` on all 51 Python files changed since base bdb0048: all checks passed)
- Test suites: pass except the known environment-only failure (see Spec Compliance); worktree, cleanup-feature and validate-feature suites not run (not touched; environment-only failures identical at base)
- CI/CD: DEGRADED (not applicable to this head: GitHub lists exactly one run for branch openspec/dispatch-contract, CI #2056 on 2e45ea7, the pre-merge PR head, conclusion success; no run exists for c83cf40)
- Choices: no ledger

## Spec Compliance

**Status**: pass

Per-directory results (each `skills/tests/<dir>` run in its own process, base-independent):

| Suite | Result |
|---|---|
| skills/tests/autopilot | 544 passed, 6 skipped |
| skills/tests/autopilot-roadmap | 147 passed |
| skills/tests/install_sh | 18 passed, 14 skipped |
| skills/tests/parallel-infrastructure | 292 passed, 2 skipped |
| skills/tests/roadmap-runtime | 182 passed, 1 skipped |
| skills/tests/shared | 136 passed, 1 skipped |
| skills/tests/supervise | 469 passed, 1 failed (known) |
| skills/autopilot/scripts/tests | 227 passed |

Totals: 1,747 passed, 24 skipped, 1 failed (known environment-only). The two project-context-refresh
shared-checkout tests are outside the touched suites and were not run. `openspec validate dispatch-contract --strict`: valid.

The single failure is the documented environment-only
`test_workflow_contract.py::test_contract_inspects_the_canonical_source_contribution`
(fails identically at base bdb0048 when run under a `.claude/` path; this run is under `.claude/worktrees/`). No other failures.

### Acceptance outcome to test mapping (proposal.md, ri-21)

1. Schemas exist and execution.py / orchestrator.py validate against them, fixtures pass: pass.
   `shared/test_dispatch_contract.py`, `roadmap-runtime/test_dispatch_schema_parity.py`,
   `supervise/test_execution_contract.py`, `supervise/test_execution.py`,
   `autopilot-roadmap/test_supervised_dispatch.py`. Legacy loading: every
   `openspec/roadmaps/**/checkpoint.json` (archived 2026-09-26, dispatch-governance,
   multiplayer-collaboration with 4 raw-token attempts, principal-credential-architecture,
   roadmap-jev-system-one-integration-assessment) loaded through `models.load_checkpoint`
   from a tmp copy (5/5 LOAD OK; real files untouched), and
   `roadmap-runtime/test_checkpoint_legacy_migration.py` (archived + live, 5 tests) passes.
2. emit-result produces a schema-valid result for every terminal/parked shape, end to end: pass.
   `autopilot/test_emit_result.py`, `autopilot-roadmap/test_dispatch_contract_e2e.py::test_every_shape_round_trips_through_emit_result_and_apply`,
   `::test_apply_refuses_a_result_the_loop_state_does_not_map_to`.
3. Closure contract test fails on any unrouted parked kind/gate: pass.
   `supervise/test_dispatch_closure.py` (`test_every_permitted_combination_has_exactly_one_path`, which derives the
   permitted set from the result schema's `oneOf` branches while `ANSWER_PATHS` derives its gates from the `Gate` enum, so
   the two sources are independent; `test_the_enumeration_covers_every_outcome_class_and_parked_kind`,
   `test_adding_a_kind_without_a_path_fails_naming_it`, `test_a_gate_the_enumeration_cannot_list_fails_loudly`,
   `test_a_path_for_a_forbidden_combination_fails`, `test_pending_gate_with_escalate_resume_is_answerable`, apply-time predicate table),
   and the apply-time refusal `autopilot-roadmap/test_supervised_dispatch.py::test_unroutable_parked_result_is_refused_before_any_callback`.
4. Posture-derived block clears on resume after posture change, human rejection does not: pass, on all three paths.
   - Standalone child: `autopilot/test_gate_check_reeval.py` (`test_a_standalone_stale_posture_block_clears_without_an_answer`,
     `test_a_standalone_block_under_a_new_posture_reparks_with_the_new_digest`, `test_an_unchanged_posture_is_not_re_evaluated`,
     `test_a_human_rejection_is_not_re_evaluated`, `test_an_operator_resume_after_a_human_rejection_lets_the_gate_be_asked_again`,
     `test_a_posture_derived_resume_does_not_end_a_human_rejection`).
   - Dispatched child and supervisor (pending_gate): `autopilot-roadmap/test_dispatch_contract_e2e.py`
     (`test_a_posture_flip_resumes_the_child_which_leaves_plan`, `test_a_human_rejection_survives_the_posture_flip`);
     `supervise/test_execution.py` (`test_a_posture_derived_block_clears_after_a_posture_change`,
     `test_an_unchanged_posture_reuses_the_prior_block`, `test_a_human_rejection_survives_a_posture_change`);
     the child applies only the supervisor's answer: `autopilot/test_gate_check_reeval.py`
     (`test_a_dispatched_child_does_not_self_re_evaluate`, `test_posture_drift_between_child_and_supervisor_blocks_auto`,
     `test_a_mismatched_approval_reference_is_refused`, `test_a_matching_reference_does_not_authorize_another_gate_or_decision`,
     `test_a_park_is_not_cleared_by_an_answer_for_another_gate`), `shared/test_approval_gate_provenance.py`.
   - Capability fingerprint (escalate_resume): `autopilot-roadmap/test_dispatch_contract_e2e.py`
     (`test_a_posture_derived_capability_block_clears_after_a_posture_flip`, added in VAL_REVIEW;
     `test_a_human_rejected_escalation_is_not_cleared_when_its_membership_changes`,
     `test_an_operator_approval_ends_a_human_rejected_escalation`, `test_an_approval_resumes_a_member_that_joined_after_the_rejection`).
5. execution_profile, review_requirements, degradations[] carried end to end; capability parks routed as single escalations: pass.
   End to end: `autopilot-roadmap/test_dispatch_contract_e2e.py::test_profile_and_degradations_travel_the_whole_chain`
   (request, launch marker, `runner.py record-degradation`, emit-result, apply, attempt record and
   apply return value) and `::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child`.
   Units: `autopilot/test_emit_result.py::test_degradations_travel_into_the_result`,
   `supervise/test_execution.py` (`test_a_marker_carries_the_supervisor_view_but_no_token`, `test_apply_persists_degradations_on_the_attempt`,
   `test_three_workers_blocked_on_one_rule_produce_one_escalation`, `test_different_missing_lanes_are_separate_escalations`),
   `autopilot/test_quorum_park.py`, `autopilot/test_convergence_loop.py`,
   `parallel-infrastructure/test_check_vendors_dispatchable.py`, `parallel-infrastructure/test_review_packet.py`.
6. checkpoint.json stores no raw launch token; default secret scan passes with no allowlist entry: pass locally by a
   one-rule proxy; the real default-ruleset scan has not run.
   `roadmap-runtime/test_landable_checkpoint.py`: `test_the_fixture_has_live_attempts_and_no_raw_token`,
   `test_the_default_generic_api_key_rule_finds_nothing` (Python port of the default gitleaks
   generic-api-key rule: keyword prefilter, regex, entropy > 3.5, applied to the committed-shape
   fixture with 2 live attempts), `test_the_rule_port_catches_a_raw_launch_token` (calibration),
   `test_no_scalar_field_name_matches_the_generic_api_key_keywords`,
   `test_gitleaks_config_has_no_entry_for_the_fixture` (no allowlist help),
   `test_the_builder_reproduces_the_fixture_shape` (fixture produced by real prepare/child_start/acknowledge).
   child_start digest verification: `supervise/test_execution.py` (`test_child_start_rejects_a_wrong_token_without_touching_the_checkpoint`,
   `test_no_raw_token_is_persisted_and_each_request_hashes_to_its_digest`, `test_resume_rotates_the_token_and_revokes_the_previous_one`),
   `autopilot-roadmap/test_supervised_dispatch.py::test_prepare_emits_v2_requests_with_digest_only_in_the_checkpoint`.
   Limits of this evidence: only gitleaks' `generic-api-key` rule is ported (the rule that flagged the raw
   tokens on PR #662); the other default rules were not applied locally.
   NOT RUN: `test_gitleaks_scan_of_the_fixture_directory_is_clean` (skipped: gitleaks binary not
   installed; binaries must not be downloaded). No CI run covers it yet either: `.github/workflows/security.yml`
   runs gitleaks only on pushes to `main` and on pull requests / merge groups targeting `main`. This change's PR
   targets `openspec/roadmap-multiplayer-collaboration`, so it does not trigger that job. The first real
   default-ruleset scan of these commits is the Security workflow on PR #662 (roadmap branch to `main`). Treat
   outcome 6 as confirmed only once that job passes.
7. Checkpoint with live attempts committed on one host reconciles on another: pass.
   `roadmap-runtime/test_cross_host_reconcile.py` (8 tests: rebind of matching worktree, refusal on diverged worktree / digest mismatch,
   reinitialize of prepared attempt, unexpired vs expired pre-go claim, post-go unknown liveness quarantined, and
   `test_a_checkpoint_checked_out_at_another_root_rebinds_without_host_a_paths`, added in VAL_REVIEW: the committed checkpoint
   names no host-A absolute path, and host B rebinds from a different checkout root after host A's tree is removed).
8. auto for proposal_approval / replan_required proceeds only with valid roadmap_approval_ref: pass.
   `shared/test_trust_posture_scope.py` (valid ref proceeds; standalone falls back to unscoped; marker-sourced refs only),
   `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto`,
   `::test_a_standalone_run_blocks_with_scope_unscoped`.

## Deploy

**Status**: N/A
Reason: work-packages.yaml `feature.deployable: false`; no service to deploy.

## CI/CD

**Status**: DEGRADED
Reason: no CI run exists for branch head c83cf40. The only run for the branch is CI #2056 on 2e45ea7 (success, pre-merge PR head). Local suites above are the evidence.

## Smoke Tests

**Status**: not applicable
Reason: skills/schemas-only change, no running service to smoke test.

## Security

**Status**: not applicable
Reason: no deployable surface for ZAP/dependency-check. Secret-scan evidence for the changed checkpoint shape is in Spec Compliance outcome 6; the real gitleaks binary was not available locally, and the Security workflow runs only for `main` (push or PR), so the first real scan is PR #662's Security job.

## E2E Tests

**Status**: not applicable
Reason: no browser or service surface.

## Review Degradations

- single_vendor_review: PLAN_REVIEW, IMPL_REVIEW and VAL_REVIEW ran claude_code only (cloud-container policy, min_quorum=1).
- coordinator_projection_forbidden: coordinator queue projection returned forbidden (expected in this environment).
- audit_sink_failed: audit sink failed for the proposal_approval, escalate_resume, pr_creation and merge gate decisions (SUBMIT_PR).
- GATEKEEPER ran via a real judge (no degradation).
- Re-validation: no new reviewer was dispatched in this VALIDATE run; VAL_REVIEW runs next and appends its own section.

## Result

**PASS** (re-validation at c83cf40) — All eight acceptance outcomes are covered by passing tests. Outcome 6's secret-scan claim rests on a one-rule port locally; the real default-ruleset gitleaks scan first runs in PR #662's Security job and must pass there before the claim is confirmed. Other not-run items are recorded above (CI status, live-service phases). The change is already merged (PR #667, 0d078ff); this report exists so the goal gate can bind VAL_REVIEW after VALIDATE.
