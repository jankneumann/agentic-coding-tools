# Validation Report: multiplayer-simulation-harness

**Date**: 2026-10-10
**Commit**: 7d18100e (validated before this report commit)
**Validated tree**: 243966cd6a8665377b007cb8648d9e0d891ec65a
**Branch**: openspec/multiplayer-simulation-harness--impl (in sync with origin/openspec/multiplayer-simulation-harness)

Deployable surface (`gate_logic.py --describe-surface` over the 98 files changed against
origin/main): `deployable: false`, "all changed paths are skills/docs/openspec". The only
required phase is Spec Compliance. The change is an offline test harness with no service, so
Deploy, Smoke, Security (live scan) and E2E are not applicable rather than skipped.

## Phase Results

- Deploy: not applicable (no deployable surface)
- Smoke: not applicable (no service, no endpoints)
- Gen-Eval: pass. `gen-eval --descriptor evaluation/descriptor.yaml --fail-threshold 1.0`, with `bin/` on PATH, reports PASS at a pass rate of 100.0%. This exercises the harness's own pack.
- Security: not applicable for live scans. Local scan: see the Security section.
- E2E: not applicable (no browser surface)
- Architecture: not run. Changes are tests, contracts and one skill script; the architecture graph is not affected by test-only additions.
- Traceability: skip (`packages/gen-eval/scripts/check_traceability.py` gate is not applicable to this harness change; contract citations are covered by `test_contracts.py`)
- Spec Compliance: pass (see below)
- Task drift: pass. 0 unchecked boxes in tasks.md, with implementation commits on the branch.
- Logs: not applicable (no deployment, no log file)
- CI/CD: no PR yet; CI runs on PR. `list_pull_requests` for head `openspec/multiplayer-simulation-harness` returned `[]`. The pre-merge CI result is unknown, not passed.
- Choices: no ledger (no `choices.json` in the change directory)

## Spec Compliance

**Status**: pass

Commands run in `skills/` (results are from this run):

| Command | Result |
|---|---|
| `uv run --extra test pytest -q tests/multiplayer-simulation` | 93 passed in 36.95 s (37.3 s wall) |
| `uv run --extra test pytest -q tests/ci_coverage tests/openspec_paths tests/autopilot/test_convergence_loop.py` | 1743 passed in 18.05 s |
| `uv run --extra test ruff check tests/multiplayer-simulation` | All checks passed |
| `openspec validate multiplayer-simulation-harness --strict` | Change is valid |
| `bin/mpsim run --scenario memory-store-blocked-dependency` | exit 0, blocked_ticks retrieval-owner=10, storage-owner=0, unblocked both true, final_tick 15 |
| `bin/mpsim run --scenario same-requirement-collision` | exit 0, collision_present=true, collision_detected=false, probes=[] |
| gen-eval pack at `--fail-threshold 1.0` | PASS, 100.0% |

Both baseline values match the characterisation the spec pins. No test was skipped, xfailed or
weakened. gen-eval wrote four report files into the working directory during the run; I deleted
them and confirmed `git status` was clean.

Scenario to test mapping (from tasks.md; every task is checked and every scenario ID has at
least one pinning test in the passing suite):

| Scenario | Pinned by |
|---|---|
| P.1, P.2, P.3, P.4 | `test_world.py`, `test_agents.py`, `test_cli.py` (P.4 exit 64) |
| C.1, C.2, C.3 | `test_oracle.py`, `test_collision_scenarios.py` |
| S.1, S.2, S.3, S.4, S.5 | `test_probes.py`, `test_cli.py` (S.4) |
| B.1, B.2, B.3, B.4, B.5, B.6 | `test_blocked_scenarios.py` |
| O.1, O.3 | `test_scaffold.py` (socket guard, CI sweep list) |
| O.2, O.4 | `test_cli.py` (env var invariance, import scan) |
| D.1, D.2 | `test_cli.py`, `test_report.py` |
| G.1, G.2, G.3 | `test_gen_eval_pack.py` |
| G.4 | `test_contracts.py`, `test_descriptor_drift.py` |
| A.1, A.2, A.3 | `test_archive_stability.py`, `test_contracts.py` |

Known non-blocking items, reported as found:

- Wall time: the harness suite takes about 35 to 37 s against the 30 s budget. The budget is
  recorded, not asserted (plan finding, iteration 3). Most of the time is the whole-tree
  path-stability guard running in a subprocess inside `test_archive_stability.py`.
- Review mode: PLAN_REVIEW and IMPL_REVIEW were single-vendor (`single_vendor_review`),
  accepted by TRUST_POSTURE.md 479dcd9.
- Open advisory ledger items: 20 and 23. Item 23 is a false finding, because `skills/uv.lock`
  is in the diff (confirmed in the changed-file list).
- `skills/autopilot/scripts/convergence_loop.py` changed (+29/-1: the `converge()` base_ref and
  bookkeeping-path scope port, operator option 2). `tests/autopilot/test_convergence_loop.py`
  passes.

## Smoke Tests

**Status**: not applicable. The change ships an offline test harness with no running service and
no health, auth or CORS endpoints, so there is nothing to smoke-test.

## Security

**Status**: not applicable. There is no deployable surface for ZAP or a dependency scan. A local
check was still made: a regex scan of added lines under `skills/`, `openspec/contracts/` and
`.github/` for API keys, private key headers, AWS and GitHub tokens, and hard-coded passwords
found nothing. The local scanners semgrep, bandit, gitleaks, trufflehog and pip-audit are not
installed in this container and were skipped. Nothing was installed from the network. The
harness also blocks network sockets in its test fixture (D9).

## E2E Tests

**Status**: not applicable. There is no UI or browser surface.

## Result

**PASS**. Spec Compliance, the only required phase, passes. Ready for PR creation and
`/cleanup-feature multiplayer-simulation-harness`. CI has not run because no PR exists yet.
