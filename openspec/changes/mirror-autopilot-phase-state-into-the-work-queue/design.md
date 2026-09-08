# Design: Coordinated Autopilot Phase Projection

## Context

`autopilot.run_loop` already persists before invoking an optional `queue_projection_fn`, and invokes that callback in `reconcile` mode after loading existing state. The coordination bridge already exposes no-raise keyed submit and reconcile helpers. The missing behavior is registration at the real coordinated host boundary, including the CLI-driven protocol used by the Autopilot skill.

## Decisions

### D1 — One adapter derives one exact projection

Add a small Autopilot-side adapter whose only input is `LoopState` plus explicit coordinator connection settings. It builds `projection_key={change_id, phase=current_phase, transition_sequence=total_iterations}` and bounded task metadata that identifies the authoritative repo-relative loop-state path. `submit` delegates to `try_submit_work`; `reconcile` delegates to `try_reconcile_work_projection`. It does not accept phase or sequence overrides and never returns queue values to the state machine.

### D2 — Registration is explicit at the execution-tier boundary

The state machine keeps `queue_projection_fn=None` by default. The coordinated host constructs and injects the adapter; local-parallel and sequential hosts do not import the bridge or construct it. The host-driven CLI exposes an explicit coordinated projection operation used immediately after canonical state writes and once in reconcile mode before resumed phase work. No environment-only inference silently turns queue traffic on.

### D3 — State persistence remains authoritative

Every path is `save_state` then projection. A state-save failure suppresses projection. A projection exception or bridge `{status: skipped|failed}` envelope is reported as degradation but never rolls back the saved phase. On resume, the adapter re-derives the desired tuple from the loaded file; it never reads a claimed/current queue row to mutate state.

### D4 — Host-driven and in-process flows share serialization

The in-process `run_loop` continues using `persist_and_project`. The CLI boundary calls a shared serializer/adapter rather than reproducing projection-key construction in `SKILL.md`. The skill protocol names the exact post-write and resume-reconcile calls, so supervise-dispatched runs inherit the same behavior automatically.

### D5 — Existing kanban data path is the proof surface

No frontend changes are planned. A live coordinator test submits successive phase generations, queries the existing queue/status surface consumed by `apps/kanban-viz`, and asserts the current phase appears within the configured poll interval. A reconciliation test kills the projection between durable save and submit, seeds a stale active generation, resumes, and verifies one current generation plus cancelled stale rows.

### D6 — Projection payloads are bounded and non-authoritative

Input metadata is allowlisted to change path, execution tier, and projection provenance; reserved identity fields appear only in `projection_key`. Descriptions and paths use existing bridge/service bounds. Logs expose status/reason/task IDs but not credentials, child transcripts, or queue payload echo.

## Failure Matrix

| Failure | Durable truth | Queue | Recovery |
|---|---|---|---|
| save fails | old loop-state | unchanged | abort before projection |
| process dies after save | new loop-state | old/missing | resume reconciliation |
| bridge/coordinator unavailable | new loop-state | old/missing | degraded result; next resume reconciles |
| duplicate publisher | same tuple | one canonical row | submit-if-absent replay |
| stale active row | loaded current tuple | stale + missing current | reconcile cancels stale and ensures current |

## Test Strategy

1. RED adapter tests for exact tuple derivation, mode routing, bounds, and response non-authority.
2. RED host/CLI tests proving each canonical transition projects only after its state file contains the same tuple.
3. RED crash/resume and duplicate replay tests.
4. Coordinator-backed integration proof for queue reconciliation and the existing kanban query path.
5. Regression tests proving absent adapter means zero coordinator imports/probes/calls.
6. Strict OpenSpec, Ruff, affected suites, truth-direction invariant, context drift, and scope validation.
