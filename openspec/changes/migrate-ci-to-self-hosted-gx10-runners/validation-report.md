# Validation Report: migrate-ci-to-self-hosted-gx10-runners

**Date**: 2026-10-11 · **Branch**: openspec/migrate-ci-to-self-hosted-gx10-runners · **Result**: PASS (on-branch scope); operator items pending

## Deploy
**Status**: skip
Not applicable: the change ships a runner kit (`deploy/gx10-runner/`) that is written and never installed on this host. No deployable service exists. Building/installing the runner image or units is HARD-BOUNDARY operator work (O3/O4).

## Smoke
**Status**: skip
Not applicable: nothing is deployed. Static smoke equivalents (unit property checks, script parsing, workflow routing evaluation) are covered under Spec Compliance.

## Security
**Status**: skip
Degraded: no gitleaks/semgrep/bandit/trivy/actionlint on this host and no ZAP target (no service). Substituted evidence: `test_fork_guard.py` (fork-PR jobs never reach self-hosted lane), `test_systemd_unit.py` (isolation properties of the unit), `test_jit_scripts.py` (no token persisted/logged, JIT config handling). No secrets introduced (kit uses `gx10-runner.env.example` only).

## E2E
**Status**: skip
Not applicable: no deployed service or browser surface.

## Spec Compliance
**Status**: pass
`openspec validate migrate-ci-to-self-hosted-gx10-runners --strict`: valid. `skills/tests/ci_runners`: 199 passed (routing expression table, manifest schema + completeness, fork guard, tool parity, systemd unit, JIT scripts, runner image, install-units, runbook cross-check, ci_wallclock). Tasks 1.1-6.1 all checked; O1-O12 unchecked by design.

## Evidence
**Status**: pass
- ci_runners 199 passed; ci_coverage + validate-feature + project-context-refresh (workflow-parsing suites) 660 passed, 5 skipped.
- Full `skills/tests` (--continue-on-collection-errors): 7966 passed, 9 skipped, 12 failed, 1 collection error. All 13 are in `multiplayer-simulation` and `roadmap-runtime`, none touched by this diff; each passes when run in isolation (multiplayer-simulation 96 passed, test_landable_checkpoint 7 passed, test_checkpoint_legacy_migration 6 passed, test_cross_host_reconcile 8 passed) = cross-directory pollution / basename collision, pre-existing and unrelated.
- ruff on `scripts/ci` and `skills/tests/ci_runners`: initially one TRY004 in `scripts/ci/ci_wallclock.py:409`; fixed with a justified `noqa` (CLI maps ValueError to a clean error, a test pins it); now clean.
- actionlint: not installed (skipped).

## CI Status
**Status**: skip
No PR exists yet; CI status pending / not applicable at this point.

## Pending-Operator Items
**Status**: skip
Not passes; require the real GX10 host or repo-admin access. On-branch evidence cited for each.
- O1 host user + linger: `test_systemd_unit.py`, `test_install_units.py`
- O2 registration credential: `test_jit_scripts.py` (token handling)
- O3 build runner image on GX10: `test_runner_image.py`, toolchain parity `test_tool_parity.py`
- O4 install/enable units, host isolation: `test_systemd_unit.py`, `test_install_units.py`
- O5 fork-PR approval repo setting: `test_fork_guard.py` (workflow-side guard only; repo setting is operator)
- O6 self-hosted dry run (green on arm64): `test_routing_expression.py`, `test_manifest_completeness.py`, `ci_wallclock verify-run` tested in `test_ci_wallclock.py`
- O7 flip lane (CI_RUNNER_LANE variable): `test_routing_expression.py` D3 table
- O8 median wall-clock drop: `ci_wallclock median/compare` in `test_ci_wallclock.py`
- O9 per-job ephemerality: `test_jit_scripts.py`, `test_systemd_unit.py`
- O10 reboot survival: `test_systemd_unit.py` (linger/restart properties)
- O11 fork-PR end-to-end: `test_fork_guard.py`
- O12 rollback drill: `test_routing_expression.py` (hosted fallback rows), runbook `test_runbook.py`
