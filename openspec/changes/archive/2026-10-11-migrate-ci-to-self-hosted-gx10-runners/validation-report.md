# Validation Report: migrate-ci-to-self-hosted-gx10-runners

**Date**: 2026-10-11 · **Branch**: openspec/migrate-ci-to-self-hosted-gx10-runners · **Result**: PASS (on-branch scope); operator items pending

**Provenance**: VALIDATE ran on code commit `58eac49a` (report committed in `9ae332eb`). VAL_REVIEW's VAL_FIX was applied on top of `3607e7cf` (tree `a47e918a`) and every suite below was re-run on the VAL_FIX working tree, which is the commit that adds this line.

## Deploy
**Status**: not applicable
Not applicable: the change ships a runner kit (`deploy/gx10-runner/`) that is written and never installed on this host. No deployable service exists. Building/installing the runner image or units is HARD-BOUNDARY operator work (O3/O4).

## Smoke Tests
**Status**: not applicable
Not applicable: nothing is deployed. Static smoke equivalents (unit property checks, script parsing, workflow routing evaluation) are covered under Spec Compliance.

## Security
**Status**: not applicable
Not applicable: no deployable surface (the surface classifier requires only Spec Compliance). Context, not a pass: no gitleaks/semgrep/bandit/trivy/actionlint on this host and no ZAP target (no service). Substituted evidence: `test_fork_guard.py` (fork-PR jobs never reach self-hosted lane), `test_systemd_unit.py` (isolation properties of the unit), `test_jit_scripts.py` (no token persisted/logged, JIT config handling). No secrets introduced (kit uses `gx10-runner.env.example` only).

## E2E Tests
**Status**: not applicable
Not applicable: no deployed service or browser surface.

## Spec Compliance
**Status**: pass
`openspec validate migrate-ci-to-self-hosted-gx10-runners --strict`: valid. `skills/tests/ci_runners`: 202 passed (199 at VALIDATE; +3 VAL_FIX regressions) (routing expression table, manifest schema + completeness, fork guard, tool parity, systemd unit, JIT scripts, runner image, install-units, runbook cross-check, ci_wallclock). Tasks 1.1-6.1 all checked; O1-O12 unchecked by design.

## Evidence
**Status**: pass
- ci_runners 202 passed; ci_runners + ci_coverage + validate-feature + project-context-refresh (workflow-parsing suites) together 862 passed, 5 skipped (VAL_FIX re-run; 859 at VALIDATE).
- Full `skills/tests` (--continue-on-collection-errors): 7966 passed, 9 skipped, 12 failed, 1 collection error. All 13 are in `multiplayer-simulation` and `roadmap-runtime`, none touched by this diff; each passes when run in isolation (multiplayer-simulation 96 passed, test_landable_checkpoint 7 passed, test_checkpoint_legacy_migration 6 passed, test_cross_host_reconcile 8 passed) = cross-directory pollution / basename collision, pre-existing and unrelated.
- Control for the claim above (VAL_REVIEW): `pytest tests/ci_runners tests/multiplayer-simulation tests/roadmap-runtime` = 477 passed, 1 skipped; the two failing directories alone = 278 passed, 1 skipped. Running this diff's test package alongside them causes no failure, so the full-suite failures come from other directories' collection order, not from `ci_runners` (unique basenames, package `__init__.py`, only `ci_wallclock*` `sys.modules` keys). No baseline full-suite run on `main` was made, so "unrelated" is inferred from this control, not proven against a main baseline.
- ruff on `scripts/ci` and `skills/tests/ci_runners`: initially one TRY004 in `scripts/ci/ci_wallclock.py:409`; fixed with a justified `noqa` (CLI maps ValueError to a clean error, a test pins it); now clean.
- actionlint: not installed (skipped).
- VAL_FIX (VAL_REVIEW pass 1): (a) runbook O4 adds a `user@<ghrunner uid>.service` drop-in with `Requires=`/`After=gx10-runner-isolation.service`, so an nft load failure stops the runners instead of only ordering them (pinned by `test_runner_user_manager_requires_the_isolation_unit`, `test_isolation_unit_is_an_early_boot_oneshot`); (b) `mint-jitconfig.sh` sweep requests now pass the same whole-budget `fits` check as the mint (pinned by `test_no_request_starts_when_it_cannot_finish_inside_the_budget`); (c) report statuses use the validate-feature vocabulary (`not applicable`, `skipped`) under the canonical gate headings (`Smoke Tests`, `E2E Tests`) and carry commit/tree provenance. `bash -n` on the mint script, ruff on `scripts/ci` + `skills/tests/ci_runners`, and `openspec validate --strict` clean after the fix.

## CI Status
**Status**: skipped
No PR exists yet; CI status pending / not applicable at this point.

## Pending-Operator Items
**Status**: skipped
Pending-operator, not passes; require the real GX10 host or repo-admin access. On-branch evidence cited for each.
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

## Validation Review

**Status**: pass

- Result: converged on pass 3 of 3 via `convergence_loop.converge()` (review_type=implementation, fix_mode=targeted), min_quorum=2.
- Lanes: `claude_code` + `codex` (verified/counting lanes per supervisor policy). Excluded as unavailable: grok (HTTP 426, CLI too old), antigravity (E2BIG/timeouts), pi (unparseable output).
- Trend (blocking/high-or-medium findings per pass): pass 1 = 3 (codex #109 high, #110, #111 medium) -> pass 2 = 2 (codex #115 high, #116 medium; report-only) -> pass 3 = 0 (codex 0 findings; claude_code 6 low verification notes).
- VAL_FIX pass 1: user@<ghrunner uid>.service drop-in Requires=/After= the isolation unit (#109); sweep requests gated on the whole mint budget (#110); report status vocabulary + provenance (#111). VAL_FIX pass 2: canonical `Smoke Tests` / `E2E Tests` headings, Security not applicable (#115, #116); DNS-resolver note in runbook (#113).
- IMPL_REVIEW round-3 fixes vendor-confirmed: mint single time budget (#99/#106), dedicated nftables isolation boot unit (#88/#107), unlabelled-job placement check (#89/#104).
- Adjudications: `.review-ledger/adjudication-val-pass{1,2}-round-1.json`. Parked advisories (low): compare() sample-attrition warning, runner_name-based hosted placement proof, fork-guard carve-out pinning only the condition prefix.
- O1-O12 remain pending-operator (not passes).
