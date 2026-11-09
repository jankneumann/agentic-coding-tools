# Validation Report: retain-static-model-until-routing-evidence

**Date**: 2026-09-25 21:30:00
**Commit**: dae6bacc771569db0b26595609fa55a5e7120070
**Validated tree**: dae6bacc (clean worktree; this report and the change-context evidence are committed on top)
**Branch**: openspec/retain-static-model-until-routing-evidence
**PR**: #624

## Environment

This run used an **isolated stack**. The shared `:54322` Postgres was never touched.

- `phase_deploy.py --env docker` → `DockerStackEnvironment`, compose project `validate-test-6ad4a6592918`, with an allocated DB port `:20875` and API port `:19831`.
- A new project name gives a fresh `postgres-data` volume, so initdb applied every migration **including 044** to a throwaway database.
- The API image was built from this branch. Runtime: podman.

## Phase Results

✓ Deploy: isolated stack up (postgres + coordinator-api, `api` profile, DEBUG logging)
✓ Smoke: 11/11 passed (health, ready, auth ×3, CORS ×2, error sanitization ×4)
○ Gen-Eval: not run in this pass (non-critical; CI `gen-eval` + `gen-eval-tests` green)
⚠ Security: DEGRADED — ZAP ran against the live API (1 informational finding); OWASP dependency-check NOT CHECKED
✓ E2E: 21/21 passed (`agent-coordinator/tests/e2e`, pinned to the isolated DB/API)
⚠ Architecture (advisory): 1 "new" cycle attributed to main, 7 file-size nits, flow validation still vacuous
✓ Traceability: gate passed (69 operations cite 37 requirements; only pre-existing gaps reported)
✓ Spec Compliance: 0 drifted tasks; `openspec validate --strict` valid; 8/15 live-verified, 7 deferred with reasons
⚠ Log Analysis: 1 pre-existing recurring error (`agent_discovery` missing), unrelated to this change
✓ CI/CD: all 24 checks passing (1 skipped by design)
○ Choices: no ledger

## Live Feature Probe (step 6.4, previously skipped)

The real client path `resolve_archetype_for_phase` ran with `ROUTING_ADAPTIVE=1` against the isolated API for **14 phases × 6 providers (84 calls)**:

| Check | Result |
|---|---|
| Differences from static (model, provider) | **0** |
| Router errors / fallbacks | **0** |
| Retention outcomes | 70 × `incumbent-infeasible-no-evidenced-alternative`, 14 × `incumbent-unresolved` (vendorless `provider=None`) |
| Rows persisted per adaptive call | 1 (flag off: 0) |
| Persisted requests carrying the incumbent | 170/170 |
| Rows with `selected IS NULL AND retention IS NULL` | 0 |
| Migration 044 | `retention` jsonb nullable, `selected` nullable, CHECK `routing_decisions_selected_or_retention` present |
| CHECK enforcement | an UPDATE to null/null is rejected (tested inside a rolled-back transaction) |
| Resolver unreachable | returned the static model/provider in 0.16s |
| No-incumbent control | 503 "no feasible model-routing candidate", no `retention` key (the pre-change behavior) |

**Why `no-evidence` did not appear.** Every catalog row in the isolated stack is excluded as `lane:unavailable`. The container has no vendor CLIs or registered agents, so no candidate is feasible. The retention table routes that case to `incumbent-infeasible-no-evidenced-alternative`, which is correct. `no-evidence` needs feasible candidates, so it can only be observed live against a coordinator with healthy lanes. **The post-deploy probe against coord.rotkohl.ai remains the check for `retention.reason = no-evidence`.** Unit and integration tests already cover it (`test_empty_catalog_evidence_keeps_incumbent_despite_alphabetical_order`, `test_every_phase_equals_static_with_the_router_on`).

## Smoke Tests

**Status**: pass

11/11 smoke tests passed against `http://localhost:19831` (isolated stack).

## Security

**Status**: DEGRADED

- **ZAP** (live, against `:19831`): ok, with 1 informational finding (Storable and Cacheable Content on `/robots.txt`).
- **OWASP dependency-check: NOT CHECKED.** The local NVD database is 15 days old, past the 7-day floor, so the scanner refuses to report a clean result. Refresh with `make security-seed-nvd`.
- Why the gap is low-risk: this branch changes **no dependency manifests** (no `pyproject.toml`, `uv.lock`, `requirements*` or `package*.json`), and CI `dependency-audit-coordinator` and `dependency-audit-skills` passed.
- Report: `security-review-report.md`.

## E2E Tests

**Status**: pass

21/21 passed (`agent-coordinator/tests/e2e`). `POSTGRES_DSN` and `BASE_URL` were pinned to the isolated stack, because the suite defaults to `:54322`.

## Architecture

**Status**: pass

Advisory mode (`gates.architecture.mode: advisory`).

- **Refresh**: the skill's `run_architecture.py --ensure` fails in this repo ("Python source directory not found: src"): it doesn't pass the Makefile's `PYTHON_SRC_DIR`. This is the same failure the PR reported. `make architecture-refresh` succeeded, and its regenerated artifacts were used for this run, then reverted rather than committed to this PR.
- **Baseline diff**: 1 `new_cycle`: `agents_config → model_routing.api → vendor_registry → agents_config`. It is **pre-existing on main**: all three import edges exist at `origin/main` (from #417). It shows as "new" only because the committed baseline graph was stale. This branch adds no cross-module imports.
- **Flow validation**: 0 findings, but **0 entrypoints checked**, even with a fresh graph. It is still vacuous for this change. Follow-up: the changed-file paths are not matching graph nodes.
- **Structural linters**: 7 medium file-size nits. All are on files that were already over the limit on main, except `model_routing/resolver.py`, which crosses 500 lines (501 → 591).

## Spec Compliance

**Status**: pass

- Task drift gate: 0 unchecked tasks.
- Traceability gate: pass (exit 0).
- `openspec validate --strict`: valid.
- `change-context.md` evidence: **8/15 pass** (live, commit `dae6bacc`), **7 deferred**. Six of those need an evidenced catalog, which cannot exist before #609 or #612; `agent-archetypes.3` is unit-only. Each row states its reason.

## Log Analysis

- **coordinator-api** (1038 lines): 0 warnings, 0 criticals, 0 tracebacks. The 4 "error" lines are the smoke suite's deliberate `/nonexistent-triggering-error` 404s.
- **postgres** (851 lines):
  - 50 × `relation "agent_discovery" does not exist`, once a minute from the watchdog poll. **This is pre-existing:** `src/watchdog.py` queries a table that no migration creates, and this branch doesn't touch that file. Tracked separately.
  - 1 × CHECK violation, which is the deliberate, rolled-back enforcement probe above.
  - `wal_level` warnings from `CREATE PUBLICATION`: expected in a local stack.

## CI/CD

All 24 checks on PR #624 passed (`dependency-update-remediation` skipped by design).

## Result

**PASS**, with one DEGRADED required phase (Security: dependency-check has stale NVD data, and no manifests changed). The merge gate needs `--accept-degraded Security`, recorded here with that rationale.

Open follow-ups (none of them block this change):

1. Run the post-deploy `select_model` probe on coord.rotkohl.ai, expecting `retention.reason = no-evidence` on healthy lanes.
2. Fix the `agent_discovery` watchdog query against a missing table (pre-existing on main).
3. Fix `run_architecture.py --ensure` in the validate-feature skill, which ignores `PYTHON_SRC_DIR`, and investigate why flow validation checks 0 entrypoints.
4. Refresh NVD data (`make security-seed-nvd`).
