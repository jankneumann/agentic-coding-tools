# VALIDATE phase report

**Change**: wire-autopilot-phase-subagents
**Phase**: VALIDATE → VAL_REVIEW (val_review_enabled=true)
**Outcome**: PASSED (env-safe phases)
**Run mode**: env-safe only (Docker-dependent phases deferred to /cleanup-feature)

## Phases run

| Phase | Result | Detail |
|---|---|---|
| spec | PASS | `openspec validate wire-autopilot-phase-subagents --strict` |
| evidence (tests) | PASS | 312 tests passing across 3 venvs (no regressions from c0c6f12 IMPL_FIX) |
| evidence (lint) | PASS | ruff clean across all changed files (skill + coordinator) |
| evidence (typecheck) | PASS | mypy clean on `agent-coordinator/src/discovery.py` and `coordination_api.py` |
| evidence (token-budget gate) | PASS | All 7 dispatching phases ≤0.25% of 200k context window |
| evidence (audit-log validator smoke) | PASS | exit codes match contract (0=match, 1=mismatch, 2=missing) |
| deploy / smoke / security / e2e | SKIPPED | Deferred to `/cleanup-feature` or `/merge-pull-requests` per project policy |

## Test breakdown

| Suite | Count | Source |
|---|---|---|
| `skills/tests/autopilot/` | 126 | + 9 from test_record_state_only_archetype.py |
| `skills/autopilot/scripts/tests/` | 80 | unchanged |
| `agent-coordinator/tests/` | 106 | unchanged |
| **Total** | **312** | |

## IMPL_FIX integration check

Round-2 fixes from c0c6f12 verified by:
* `test_record_state_only_archetype.py` (8 new tests) covers the new
  `phase_agent.record_state_only_archetype` helper end-to-end + the
  `_phase_init` / `_phase_submit_pr` resolver wires (closes R-005 gap).
* `runner.py record-state-only-archetype` smoke-tested via real coordinator
  (returned `runner` archetype for INIT, persisted to loop-state.json).
* `_PHASE_TASKS` strings inspected for IMPLEMENT / IMPL_REVIEW / VALIDATE
  outcomes — now match TRANSITIONS keys exactly.
* `coordination_mcp.discover_agents` response dict diff inspected — adds
  `phase_archetype` field, no other change.
* `apply_phase_outcome` replay path inspected — `_atomic_unlink(_cache_path)`
  now sweeps orphaned cache.

## Acknowledged findings (deferred to follow-up issues)

| ID | Vendor | Severity | Note |
|---|---|---|---|
| C-R-003 | claude | high | Token-budget gate uses synthetic data; can't catch realistic prompt growth (~0.4% vs 60%/75% thresholds). Filed as follow-up. |
| C-R-004 | claude | medium | `audit_log_validator.expected_phase_models_from_loop_state` hardcodes the 7-phase happy path; FIX iterations produce false counts. |
| C-R-006 | claude | medium | `AUTOPILOT_PHASE_MODEL_OVERRIDE` silently drops `system_prompt`. Design-intent per the override docstring; tracked for clarification. |
| C-R-007 | claude | medium | Network timeout fallback test stubs the bridge function rather than testing absorption inside it. |
| C-R-008 | claude | low | `_DEFAULT_PHASE_MODEL` (audit_log_validator) and `_FALLBACK_MODEL_BY_PHASE` (token_budget_check) disagree on IMPLEMENT default. |
| C-R-009 | claude | low | `apply_phase_outcome` silently aborts on missing/malformed loop-state.json. Behavior matches spec (no scenario for missing-file case). |
| G-R-003 | gemini | low | `coordination_mcp.heartbeat` MCP tool doesn't accept `phase_archetype`. HTTP API does; MCP parity gap. |
| G-R-005 | gemini | low | Cache checksum mismatch silently writes `phase_archetype = None`. Design-intent per spec. |

False positive (no fix):
* G-R-001 (gemini, high): replay phase-check claimed missing at line 947.
  In fact present at lines 949-953: `state.get("previous_phase") == phase or state.get("current_phase") == phase`.

## Next phase

VAL_REVIEW (val_review_enabled=true) — multi-vendor convergence on validation evidence.
