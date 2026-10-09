# Validation Report: dispatch-contract

**Date**: 2026-10-09
**Commit**: 7cc9180c3ea49a0a9b08618d376bf0c2793bdccc
**Branch**: openspec/dispatch-contract

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
- Lint: pass (`ruff check` on every changed Python file/dir: all checks passed)
- Test suites: pass except the known environment-only failure (see Spec Compliance)
- CI/CD: DEGRADED (not checked; GitHub MCP lists zero workflow runs for branch openspec/dispatch-contract and no PR exists yet)
- Choices: no ledger

## Spec Compliance

**Status**: pass

Per-directory results (each `skills/tests/<dir>` run in its own process, base-independent):

| Suite | Result |
|---|---|
| skills/tests/autopilot | 533 passed, 6 skipped |
| skills/tests/autopilot-roadmap | 144 passed |
| skills/tests/install_sh | 18 passed, 14 skipped |
| skills/tests/parallel-infrastructure | 292 passed, 2 skipped |
| skills/tests/roadmap-runtime | 181 passed, 1 skipped |
| skills/tests/shared | 134 passed, 1 skipped |
| skills/tests/supervise | 459 passed, 1 failed (known) |
| skills/autopilot/scripts/tests/test_autopilot.py | 48 passed |

The single failure is the documented environment-only
`test_workflow_contract.py::test_contract_inspects_the_canonical_source_contribution`
(fails identically at base bdb0048 when run under a `.claude/` path). No other failures.

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
   `supervise/test_dispatch_closure.py` (`test_every_permitted_combination_has_exactly_one_path`,
   `test_adding_a_kind_without_a_path_fails_naming_it`, `test_pending_gate_with_escalate_resume_is_answerable`, apply-time predicate table).
4. Posture-derived block clears on resume after posture change, human rejection does not: pass.
   `autopilot/test_gate_check_reeval.py` (`test_a_standalone_stale_posture_block_clears_without_an_answer`,
   `test_a_human_rejection_is_not_re_evaluated`), `autopilot-roadmap/test_dispatch_contract_e2e.py`
   (`test_a_posture_flip_resumes_the_child_which_leaves_plan`, `test_a_human_rejection_survives_the_posture_flip`),
   `shared/test_approval_gate_provenance.py`.
5. execution_profile, review_requirements, degradations[] carried end to end; capability parks routed as single escalations: pass.
   `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child`,
   `autopilot/test_quorum_park.py`, `autopilot/test_convergence_loop.py`,
   `parallel-infrastructure/test_check_vendors_dispatchable.py`, `parallel-infrastructure/test_review_packet.py`.
6. checkpoint.json stores no raw launch token; default secret scan passes with no allowlist entry: pass (with one sub-check not run).
   `roadmap-runtime/test_landable_checkpoint.py`: `test_the_fixture_has_live_attempts_and_no_raw_token`,
   `test_the_default_generic_api_key_rule_finds_nothing` (Python port of the default gitleaks
   generic-api-key rule: keyword prefilter, regex, entropy > 3.5, applied to the committed-shape
   fixture with 2 live attempts), `test_the_rule_port_catches_a_raw_launch_token` (calibration),
   `test_no_scalar_field_name_matches_the_generic_api_key_keywords`,
   `test_gitleaks_config_has_no_entry_for_the_fixture` (no allowlist help),
   `test_the_builder_reproduces_the_fixture_shape` (fixture produced by real prepare/child_start/acknowledge).
   child_start digest verification: `roadmap-runtime/test_delegated_checkpoint.py`, `autopilot-roadmap/test_supervised_dispatch*.py`.
   NOT RUN: `test_gitleaks_scan_of_the_fixture_directory_is_clean` (skipped: gitleaks binary not
   installed; binaries must not be downloaded). The CI gitleaks job remains the real-binary check.
7. Checkpoint with live attempts committed on one host reconciles on another: pass.
   `roadmap-runtime/test_cross_host_reconcile.py` (7 tests: rebind of matching worktree, refusal on diverged worktree / digest mismatch,
   reinitialize of prepared attempt, unexpired vs expired pre-go claim, post-go unknown liveness quarantined).
8. auto for proposal_approval / replan_required proceeds only with valid roadmap_approval_ref: pass.
   `shared/test_trust_posture_scope.py` (valid ref proceeds; standalone falls back to unscoped; marker-sourced refs only),
   `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto`,
   `::test_a_standalone_run_blocks_with_scope_unscoped`.

## Smoke Tests

**Status**: not applicable
Reason: skills/schemas-only change, no running service to smoke test.

## Security

**Status**: not applicable
Reason: no deployable surface for ZAP/dependency-check. Secret-scan evidence for the changed checkpoint shape is in Spec Compliance outcome 6; the real gitleaks binary was not available locally (CI covers it).

## E2E Tests

**Status**: not applicable
Reason: no browser or service surface.

## Review Degradations

- single_vendor_review: PLAN_REVIEW and IMPL_REVIEW ran claude_code only (cloud-container policy, min_quorum=1).
- coordinator_projection_forbidden: coordinator queue projection returned forbidden (expected in this environment).
- GATEKEEPER ran via a real judge (no degradation).

## Result

**PASS** — All eight acceptance outcomes are covered by passing tests. Not-run items are recorded above (gitleaks binary, CI status, live-service phases). Ready for `/cleanup-feature dispatch-contract`.
