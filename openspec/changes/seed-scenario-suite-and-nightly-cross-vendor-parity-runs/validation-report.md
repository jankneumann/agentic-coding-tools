# Validation Report: seed-scenario-suite-and-nightly-cross-vendor-parity-runs

**Date**: 2026-10-11
**Commit**: 41ada8a653dd33477687b7b62aeb2330cd265e3c
**Branch**: openspec/seed-scenario-suite-and-nightly-cross-vendor-parity-runs

Scope note: this change is a `packages/agent-scenarios` library/CLI plus systemd
TEMPLATES and docs. There is no service to deploy. `gate_logic --describe-surface`
reports `deployable: true` only because the branch diff against the (stale) merge-base
also contains agent-coordinator paths; the container deploy is therefore not applicable,
and Smoke/E2E are defined as exercising the CLI end-to-end locally with FakeExecutor
(no real vendor CLI, no coordinator writes, no systemd/crontab install).

## Deploy

**Status**: not applicable
No service. No container was started. Templates in `packages/agent-scenarios/deploy/systemd/` are NOT installed (verified: no `agent-scenarios*` unit in `~/.config/systemd/user`, `systemctl --user list-unit-files`, or crontab).

## Smoke Tests

**Status**: pass
- `agent-scenarios validate --scenarios scenarios`: 11 scenarios load, each with >=2 vendors and 4 gates.
- `agent-scenarios nightly --dry-run` with a temp config (example shape, real scenarios dir): `would_run: true`, vendors claude+codex, 22 planned pairs, caps evaluated, nothing written.
- `nightly.example.yaml` dry-run as shipped (`enabled: false`, unexpanded `~` paths) fails safe with a clear error and `would_run: false`.
- Package gates: pytest 209 passed / 1 skipped; mypy clean (16 files); ruff clean.

## Security

**Status**: pass
Not checked: OWASP dependency-check / ZAP (no HTTP service to scan; no new dependencies surface beyond the package lockfile).
Checked:
- Hermetic env scrub: `HERMETIC_SCRUB` denylist covers COORDINATION_API_KEY, COORDINATOR_*/AGENT_COORDINATOR_* URLs/ports, GH_TOKEN, GITHUB_TOKEN, GH_ENTERPRISE_TOKEN, GITHUB_ENTERPRISE_TOKEN, CF_ACCESS_CLIENT_ID/SECRET. Tests pass: `test_executor_subprocess_env_is_hermetic`, `test_empty_scrub_still_applies_builtin_denylist`, `test_env_set_cannot_reintroduce_scrubbed_name`, `test_denylist_covers_bridge_variables`, `test_config_schema_env_set_denylist_matches_executor`, `test_default_executor_factory_wires_hermetic_settings` (17 env/scrub/flush tests passed).
- Systemd units and timers are templates only and not installed; shipped config is `enabled: false`.
- No TRUST_POSTURE change, no live coordinator writes (gap emitter used test sinks).

## E2E Tests

**Status**: pass
End-to-end CLI runs with FakeExecutor (`validation-evidence/drive_fake_nightly.py`):
- 2-vendor nightly over the full 11-scenario suite: rc 0, 22 results + 1 run record, all `deterministic_status: pass`, vendors {claude, codex} x families {plan, implement, validate, merge} (`validation-evidence/fake-2vendor-nightly-results.jsonl`).
- `results trend --group-by vendor,skill`, `results latest`, `results query`: rc 0 (`validation-evidence/results-trend-by-vendor-skill.json`).
- Broken-skill path: `tests/test_acceptance_broken_skill.py` (breaks validate-feature SKILL.md -> both vendors `fail` on `report-has-status`, 2 capability-gap spool entries tagged `source:scenario-parity` + `affected_skill:validate-feature`, /improve-harness `rank_findings` ranks it with frequency 2; restoring the skill passes). `gaps flush` against a local stub: 6 flush tests pass.
- Live vendor nightly run: PENDING OPERATOR (tasks 7.1-7.6).

## Spec Compliance

**Status**: pass
- OpenSpec: `openspec validate` valid. Traceability gate (`check_traceability.py --scope change`): exit 0, 75 operations cite 44 requirements.
- Task drift: 6 unchecked boxes remain (7.1-7.6), all operator-only GX10 rollout steps (dedicated user, real CLIs/keys, systemd install, live drill, one-week baseline). They cannot be performed by an agent and are explicitly out of the hard boundary; recorded as deferred operator tasks, not code drift. All implementation tasks (1.x-6.x) are checked.
- Acceptance outcomes:
  1. >=10 seed scenarios across plan/implement/validate/merge, >=2 vendors each: 11 scenarios, all claude+codex; fake 2-vendor nightly green. Live run: pending operator.
  2. Deliberately-broken skill -> suite fails + capability-gap finding: pass (above).
  3. Results queryable per vendor per skill over time: pass (`results trend --group-by vendor,skill`, `latest`, `query`).
- Deferred follow-up: choices/review ledger item 78 (parked at IMPL_REVIEW).

## CI

**Status**: skipped
No PR exists yet for this branch; CI pending.

## Result

**PASS** — framework validated; live nightly rollout (tasks 7.x) remains an operator task. Ready for PR/cleanup.
