# Validation Report: wire-supervise-execution-through-the-dispatch-fn-seam

**Date**: 2026-09-01 03:39:47 EDT
**Commit**: 3b5a1fb06d8ae3662414985d06092016015a6c96
**Validated tree**: 94fe2d72c092b94ea661b75e5c7936376472178d
**Branch**: openspec/wire-supervise-execution-through-the-dispatch-fn-seam
**PR**: #451

## Phase Results

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | not applicable | The declared surface is nondeployable: skills, deterministic scripts, tests, and OpenSpec artifacts only. |
| Smoke | not applicable | No live service is introduced or modified. |
| Gen-Eval | fail (non-critical) | The cli-augmented descriptor loaded the active change, but its mandatory health check could not reach localhost:8081 in this nondeployable validation environment. |
| Security | not applicable | No deployable surface exists; live OWASP/ZAP scanning does not apply. |
| E2E | not applicable | Browser/live-service E2E does not apply. The deterministic host-session integration suite passed 2/2. |
| Architecture | warn | Fresh graph and baseline diff found 0 new nodes, edges, cycles, routes, or tables; scoped flow validation found 0 issues. Advisory structural lint reported 15 file-size nits. |
| Spec Compliance | fail | 7/8 requirements verified. A minimal reproduction proves the deferred peer of an overlapping pair later carries proven_disjoint instead of the required serial_indeterminate proof. |
| Evidence | fail | Seven packages are declared. Only wp-contracts has a durable work-result, and it records plan revision 2 rather than current revision 3; six results are absent. |
| Logs | not applicable | No deployment or live-service log was produced. |
| CI/CD | pass | All 15 substantive GitHub checks passed at the exact PR head; one dependency-remediation job was intentionally skipped. |

## Deploy

**Status**: not applicable

The surface classifier returned deployable=false from the change declaration. Container-backed phases are not applicable rather than skipped.

## Smoke Tests

**Status**: not applicable

No live service surface exists.

## Gen-Eval

**Status**: fail

The repository descriptor was detected and cli-augmented mode loaded the active OpenSpec change. With service startup disabled for this nondeployable change, the descriptor still required http://localhost:8081/health and exited non-zero after five attempts. This phase is non-critical, but no local gen-eval pass is claimed. The PR's CI gen-eval check passed.

## Security

**Status**: not applicable

No deployable surface exists, so live dependency/ZAP scanning is outside the applicable validation surface. Security-sensitive context bounding, worktree containment, correlation, takeover, and transcript-exclusion behavior is exercised by the deterministic feature suites.

## E2E Tests

**Status**: not applicable

No browser or live-service E2E applies. The two-child host-session integration test passed 2/2 and exercises concurrency, overlap serialization, worktree isolation, exact result correlation, and transcript exclusion.

## Architecture

**Status**: warn

The repository-specific architecture producer refreshed successfully and a second ensure was fresh. Baseline diff against ae9576a56638d5c165792654c1b00c7451bafead reported 0 added/removed nodes, 0 added/removed edges, 0 new cycles, 0 new high-impact modules, 0 untested new routes, and 0 new tables. Scoped flow validation covered 81 PR files with 0 findings.

Architecture mode is advisory. Structural lint reported 15 medium-criticality nits, all file-size findings: seven generated context checkpoints, three JSON schema artifacts, three touched Python modules, and two test modules. These warnings do not override the separate blocking spec defect.

## Spec Compliance

**Status**: fail

See [change-context.md](./change-context.md) for the requirement traceability matrix.

**Summary**: 7/8 requirements verified, 1 gap, 0 deferred.

Blocking scenario: roadmap-orchestration.2 requires every request affected by overlap or indeterminate scope to carry proof: serial_indeterminate. At the validated commit, a two-call reproduction yields:

- first batch: ri-01 has serial_indeterminate; ri-02 is deferred
- second batch: ri-02 is emitted alone with proven_disjoint

The existing end-to-end test asserts serialization and maximum live handles, but it does not assert the proof on the second request.

### Critical sub-gates

- Task checkbox drift: pass (0 unchecked of 20; 44 feature commits).
- Requirement-to-contract traceability: environment failure under the skill-prescribed fallback interpreter because packages/gen-eval/.venv is absent and python3 lacks pydantic. The same change-scoped gate exits 0 under the repository-managed skills virtual environment (68 operations cite 36 requirements), but that alternate run is evidence only and is not treated as a waiver.
- Strict OpenSpec: pass (95/95 active items).

## Evidence Completeness

**Status**: fail

The seven-package plan, contracts, DAG, context-impact declarations, overlap checks, and locks validate. Durable result evidence does not:

- wp-contracts/work-result.json is schema-valid, scope-compliant, and verification-consistent, but records plan_revision 2 while work-packages.yaml declares revision 3.
- No durable work result exists for wp-runtime-state, wp-scheduler, wp-orchestrator, wp-host-adapter, wp-supervise, or wp-integration.
- Cross-package revision, modified-file overlap, verification, and escalation consistency therefore cannot be established.

## Log Analysis

**Status**: not applicable

No deployment was started.

## CI/CD

**Status**: pass

PR #451 points to exact head 3b5a1fb06d8ae3662414985d06092016015a6c96. GitHub reports all 15 substantive checks successful; dependency-update-remediation was intentionally skipped.

## Quality Checks

- Focused feature suites: 370 passed.
- Focused host-session integration: 2 passed.
- Host-assisted invariant: 2 passed.
- Ruff: pass on changed Python implementation and tests.
- Strict OpenSpec: 95 passed, 0 failed.
- Work-package schema/DAG/contracts/context-impact/scope/lock gates: pass.
- Runtime skill mirrors: pass.
- Git diff check: one generated session-log blank-line-at-EOF warning at the validated commit; validation session-log sanitization is expected to reconcile this bookkeeping issue.

## Result

**FAIL** - Not ready for cleanup or merge. Return to /iterate-on-implementation with a failing test for the second overlapping request's proof, regenerate all seven package result records at plan revision 3/contracts revision 1, provision the prescribed traceability interpreter, and re-run /validate-feature.
