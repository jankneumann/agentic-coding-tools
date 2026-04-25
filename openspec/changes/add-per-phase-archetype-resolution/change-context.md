# Change Context: add-per-phase-archetype-resolution

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-archetypes.1 | specs/agent-archetypes/spec.md — Per-Phase Archetype Mapping | `archetypes.yaml` gains optional `phase_mapping`; loader exposes it as `dict[str, PhaseMappingEntry]`; raises `ValueError` on undefined archetype reference | contracts/schemas/archetypes-config-v2.schema.json | D1, D11 | --- | agent-coordinator/tests/test_agents_config.py::test_load_archetypes_with_phase_mapping; ::test_load_archetypes_legacy_v1; ::test_load_archetypes_undefined_archetype | --- |
| agent-archetypes.2 | specs/agent-archetypes/spec.md — Phase Archetype Resolution Function | `resolve_archetype_for_phase(phase, signals) -> ResolvedArchetype` looks up phase, resolves archetype, calls `resolve_model(..., phase=phase)`, returns `(model, system_prompt, archetype, reasons)`; ignores unlisted signals; raises `KeyError` on unknown phase | --- | D3, D11 | --- | agent-coordinator/tests/test_agents_config.py::test_resolve_for_phase_known; ::test_resolve_for_phase_unknown; ::test_resolve_for_phase_with_escalation | --- |
| agent-archetypes.3 | specs/agent-archetypes/spec.md — Phase Archetype Resolution Endpoint Contract | Endpoint returns `200` with `{model, system_prompt, archetype, reasons}`; `400` malformed; `401` no key; `404` unknown phase; `500` config error; requires `X-API-Key` | contracts/openapi/v1.yaml#/paths/~1archetypes~1resolve_for_phase | D2 | --- | agent-coordinator/tests/test_coordination_api.py::test_resolve_for_phase_200; ::test_resolve_for_phase_400_missing_phase; ::test_resolve_for_phase_401_no_key; ::test_resolve_for_phase_404_unknown_phase | --- |
| agent-coordinator.1 | specs/agent-coordinator/spec.md — Phase Archetype Resolution Endpoint | `POST /archetypes/resolve_for_phase` served by `coordination_api.py`, requires `X-API-Key`, delegates to `resolve_archetype_for_phase`, returns 200/400/404, logs successful resolutions to audit with `operation="resolve_archetype_for_phase"`, `agent_id`, `phase`, `archetype`, `model` | contracts/openapi/v1.yaml#/paths/~1archetypes~1resolve_for_phase | D2 | --- | agent-coordinator/tests/test_coordination_api.py::test_resolve_for_phase_200; ::test_resolve_for_phase_audit_log_entry; ::test_resolve_for_phase_404_unknown_phase | --- |
| agent-coordinator.2 | specs/agent-coordinator/spec.md — LoopState Phase Archetype Field | `LoopState.phase_archetype: str \| None`; `schema_version` bumped 2→3; defaults to `None`; persists in `loop-state.json`; emitted in status report; v2 snapshots load with `phase_archetype=None` and rewrite to v3 on save | contracts/schemas/loop-state-v3.schema.json | D7 | --- | skills/tests/autopilot/test_loop_state.py::test_new_loop_state_default; ::test_load_v2_snapshot_migrates; ::test_phase_archetype_round_trip | --- |
| agent-coordinator.3 | specs/agent-coordinator/spec.md — Status Report Payload Phase Archetype Field | `POST /status/report` accepts and persists optional `phase_archetype`; older clients without the field still get 200; `GET /status/agents` exposes the value | --- | D7 | --- | agent-coordinator/tests/test_coordination_api.py::test_status_report_with_phase_archetype; ::test_status_report_without_phase_archetype | --- |
| agent-coordinator.4 | specs/agent-coordinator/spec.md — Phase Archetype Resolution Bridge Helper | `coordination_bridge.try_resolve_archetype_for_phase(phase, signals) -> dict \| None` returns dict on 200, `None` on any failure (network/timeout/non-200/malformed JSON); structured warning logged on failure; never raises | contracts/openapi/v1.yaml#/paths/~1archetypes~1resolve_for_phase | D4, D9 | skills/coordination-bridge/scripts/coordination_bridge.py; skills/tests/coordination-bridge/test_archetype_resolve.py | skills/tests/coordination-bridge/test_archetype_resolve.py::test_resolve_success_returns_dict; ::test_resolve_5xx_returns_none_and_warns; ::test_resolve_timeout_returns_none; +7 more | --- |
| skill-workflow.1 | specs/skill-workflow/spec.md — Per-Phase Archetype Resolution in Autopilot | `_build_options(phase, state_dict)` extracts signals via `_extract_signals_for_phase`, calls bridge, sets `options["model"]` and `options["system_prompt"]`, records `state_dict["_resolved_archetype"]`; covers all 13 non-terminal phases | --- | D5, D6, D12, D13 | --- | skills/tests/autopilot/test_build_options.py::test_plan_resolves_to_architect; ::test_implement_escalation_signals; skills/tests/autopilot/test_phase_archetype_e2e.py::test_full_autopilot_run_records_archetypes | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md — Per-Phase Archetype Resolution Override | `AUTOPILOT_PHASE_MODEL_OVERRIDE` env var (`<PHASE>=<model>[,...]`) takes precedence over archetype model; only `model` set, `system_prompt` left to harness default; unknown phases warned and ignored; unknown models pass through | --- | D8 | --- | skills/tests/autopilot/test_phase_override.py::test_override_forces_model; ::test_override_unknown_phase_warns; skills/tests/autopilot/test_phase_override_e2e.py::test_override_path_used | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md — Per-Phase Archetype Resolution Failure Mode | Bridge `None` triggers fallback: no `model`/`system_prompt` injection, `LoopState.phase_archetype = None`, structured warning with phase + reason + override hint, phase still dispatches | --- | D9 | --- | skills/tests/autopilot/test_build_options.py::test_bridge_failure_fallback; skills/tests/autopilot/test_phase_archetype_failure_e2e.py::test_coordinator_unreachable_continues | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1: phase_mapping in archetypes.yaml | Single source of truth co-located with archetypes | (pending) | Approach 2/3 rejected at Gate 1 — splits config or muddies signal abstraction |
| D2: POST /archetypes/resolve_for_phase | Reusable beyond autopilot; carries reasons[] for audit | (pending) | Skills-side mapping (Approach 2) reduces API to thin shim |
| D3: phase kwarg on resolve_model | Backward-compatible additive metadata | (pending) | Avoids new resolve fn for pure record-keeping |
| D4: coordination_bridge.try_resolve_archetype_for_phase | Mirrors existing try_* failure-tolerant pattern | (pending) | Direct urllib calls in phase_agent would duplicate bridge plumbing |
| D5: _build_options sets model + system_prompt | Full archetype semantics (persona + model) | (pending) | model-only injection rejected — loses archetype's role definition |
| D6: _PHASE_TASKS extends to all 13 phases | Uniform phase taxonomy, no special cases | (pending) | Per-phase if/else in build_options would scatter the registry |
| D7: LoopState.phase_archetype + schema bump 2→3 | Coordinator is the audit authority | (pending) | per-phase dict (`phase_archetype: dict[str,str]`) rejected — current-phase semantics simpler |
| D8: AUTOPILOT_PHASE_MODEL_OVERRIDE env var | Sufficient for cloud-harness without flag plumbing | (pending) | CLI flag rejected — adds plumbing without capability |
| D9: Bridge failure → graceful fallback | Don't block autopilot on coordinator availability | (pending) | Hard-fail rejected — too brittle for cloud-harness |
| D10: Read-only file lock on convergence_loop.py | Visibility coordination with harness-engineering-features | (pending) | Lock-based pattern matches project's coordinator-mediated coordination |
| D11: Default phase mapping (architect/reviewer/implementer/analyst/runner) | Initial cut tunable via YAML without code changes | (pending) | Single mapping table avoids per-phase code branches |
| D12: Per-phase signal lists in phase_mapping | Explicit signal contract per phase | (pending) | Free-form signals (Approach 3) muddies resolve_model abstraction |
| D13: INIT/SUBMIT_PR record archetype but skip dispatch | Audit consistency without scope creep | (pending) | Promoting to sub-agent dispatches expands scope unnecessarily |

## Coverage Summary

- **Requirements traced**: 0/10 (Phase 2 will populate Files Changed for each)
- **Tests mapped**: 10 requirements have at least one test planned
- **Evidence collected**: 0/10 (Phase 3 fills after `/validate-feature` runs)
- **Gaps identified**: ---
- **Deferred items**: ---
