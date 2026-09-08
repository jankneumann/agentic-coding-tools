# Design: Coordinated Autopilot Phase Projection

## Context

`autopilot.run_loop` already persists before invoking an optional `queue_projection_fn`, and invokes that callback in `reconcile` mode after loading existing state. The coordination bridge already exposes no-raise keyed submit and reconcile helpers. The missing behavior is registration at the real coordinated host boundary, including the CLI-driven protocol used by the Autopilot skill.

## Decisions

### D1 — One adapter derives one exact projection

Add a small Autopilot-side adapter whose only input is `LoopState` plus explicit coordinator connection settings. It derives `projection_key={change_id, phase=current_phase, transition_sequence=total_iterations}` and the bounded payload in D6. Submit mode uses the head-advance algorithm in D7; reconcile mode directly repairs from durable state. Successful results use D9 coordinator-only label repair. The adapter accepts no identity overrides and never returns queue values to the state machine.

### D2 — Registration is explicit at the execution-tier boundary

The state machine keeps `queue_projection_fn=None` by default. Only an explicitly selected coordinated host constructs and injects the adapter; local-parallel and sequential hosts follow D10. The host CLI exposes the canonical `init` and `transition` writers from D8 plus `project-state --mode submit|reconcile`. `project-state` requires explicit coordinator connection settings, loads the just-written state itself, and never changes state. No environment-only inference silently enables queue traffic.

### D3 — State persistence remains authoritative

Every coordinated loop-state write follows the D8 write matrix: durable save first, then projection, including idempotent replay when identity is unchanged. A state-save failure suppresses projection. A projection exception or bridge `{status: skipped|failed}` envelope is reported as degradation but never rolls back the saved phase. On resume, the adapter re-derives the desired tuple from the loaded file; it never reads a claimed/current queue row to mutate state.

### D4 — Host-driven and in-process flows share serialization

The in-process `run_loop` continues using `persist_and_project`. The CLI boundary calls `project-state` and a shared serializer/adapter rather than reproducing projection-key construction in `SKILL.md`. `apply-outcome` remains phase-state bookkeeping only and does not silently enable coordinator traffic. The skill protocol names the exact post-write and resume-reconcile calls, so supervise-dispatched runs inherit the same behavior automatically.

### D5 — Existing kanban data path is the proof surface

No frontend changes are planned. Migration `037_autopilot_phase_projection_visibility.sql` extends the work-queue notification trigger so a label update adding or removing `projection:autopilot-phase` emits a change-scoped projection event. The trigger derives `change_id` from NEW labels and falls back to OLD labels on removal. `event_stream.py` converts that event to a fresh SSE `snapshot`, allowing an already connected board to add the new row and remove stale rows without waiting for polling fallback. A live coordinator test advances at least three generations (including direct ESCALATE sequence advancement), repairs the D9 labels, seeds more than 50 ordinary lower-priority issues, queries `/issues/list` with the existing `change:<id>` label exactly as `apps/kanban-viz` does, and asserts both a connected SSE client and polling fallback show the priority-1 current phase within 5 seconds. A reconciliation test kills projection and label cleanup at each durability boundary, resumes, and verifies one active labelled projection generation plus cancelled and unlabelled stale projection rows.

### D6 — Projection payloads are bounded and non-authoritative

Input metadata is allowlisted to change path, execution tier, and projection provenance; reserved identity fields appear only in `projection_key`. Descriptions and paths use existing bridge/service bounds. The adapter-owned row labels are exactly `change:<change_id>` and `projection:autopilot-phase`; D9 makes whole-array replacement and cleanup set-idempotent without touching ordinary issues. Logs expose status/reason/task IDs but not credentials, child transcripts, or queue payload echo.

## Failure Matrix

| Failure | Durable truth | Queue | Recovery |
|---|---|---|---|
| save fails | old loop-state | unchanged | abort before projection |
| process dies after save | new loop-state | old/missing | resume reconciliation |
| bridge/coordinator unavailable | new loop-state | old/missing | degraded result; next resume reconciles |
| canonical row created but label update fails | new loop-state | current row not board-visible | degraded result; resume reconciles and re-labels |
| duplicate publisher | same tuple | one canonical row | submit-if-absent replay |
| stale active row | loaded current tuple | stale + missing current | reconcile cancels stale and ensures current |

## Test Strategy

1. RED adapter tests for exact tuple derivation, mode routing, canonical task-ID correlation, idempotent labeling, partial label failure, bounds, and response non-authority.
2. RED host/CLI tests proving each canonical transition projects only after its state file contains the same tuple.
3. RED crash/resume and duplicate replay tests.
4. Coordinator-backed integration proof for queue reconciliation and the existing kanban query path.
5. Import/module and fail-fast call-spy regressions proving D10 projection isolation while allowing pre-existing coordinator detection/archetype use.
6. Strict OpenSpec, Ruff, affected suites, truth-direction invariant, context drift, and scope validation.


## Round 1 convergence amendments

### D7 — Submit mode advances the projection head

The adapter derives the only identity from the loaded `LoopState`. Submit mode first calls `try_submit_work`. The bridge represents a projection conflict as `status=error`, `status_code=409`, with the problem document under `response`; only `response.detail` equal to `reconciliation_required` falls through to `try_reconcile_work_projection`. `enter_escalate` is corrected to increment `total_iterations` exactly once whenever it changes the phase to ESCALATE, matching `_apply_transition` and preventing same-sequence phase collisions. `projection_generation_mismatch`, `stale_projection`, every other 409 detail, and all other skipped/failed/error envelopes remain degraded. Reconcile mode calls `try_reconcile_work_projection` directly. Tests project at least three successive generations so first-insert and same-generation replay cannot hide an inverted mode mapping.

### D8 — The prose host gets canonical writers

Add `runner.py init` and `runner.py transition --outcome <outcome>`. `init` idempotently creates the canonical INIT state; `transition` loads state, invokes the existing `_apply_transition`, and saves it. Every direct `enter_escalate` path increments `total_iterations` exactly once before save, including gate parks and phase exceptions. The SKILL host no longer advances phases only in prose. It calls `project-state --mode submit` after every successful loop-state mutation (`init`, `transition`, `apply-outcome`, `record-state-only-archetype`, and `gate-answer`). For `gate-check`, documented exits 0, 3, and 4 mean the decision/park was durably recorded and are followed by submit projection before ask, continue, or stop; exits 1 and 2 suppress projection. On resume, reconcile runs immediately after loading state and before pending-gate handling or phase work.

`run_loop` currently has no production caller; as a library contract it accepts an explicitly injected adapter and routes every `save_state` site through `persist_and_project`, including initial creation, gate-session flushes, pending/stay paths, transition refusals, ESCALATE writes, and terminal memory bookkeeping. `_GateSession` gains an optional projection callback defaulting to None: only `run_loop` passes it, while `runner.py` leaves it unset because the CLI host projects after the command returns. Re-projecting an unchanged identity is an intentional idempotent replay. A failed save never invokes projection.

### D9 — Board-visible rows and label repair

Projection rows use `task_type="issue"` and priority 1. They are visible to the existing issue-only `/issues/list` path. Migration 037 adds the missing `task_type <> "issue"` predicate to `claim_task`, aligning enforced claim behavior with the existing issue-service contract and making projection and all ordinary issue rows unclaimable even when `task_types` is absent. Their bounded, adapter-owned label set is exactly `change:<change_id>` plus `projection:autopilot-phase`. Add additive coordinator-only bridge helpers for issue list/update that always target the configured coordinator HTTP endpoint and never consult the GitHub issue backend. Full-array replacement is safe only for these exclusively owned projection rows.

After a successful submit/reconcile response, the adapter labels the returned canonical task ID, clears labels on returned cancelled projection IDs, and in reconcile mode lists up to the coordinator maximum of 100 concurrently double-labelled rows with both adapter-owned labels and clears any non-canonical leftovers from an interrupted cleanup. Canonical labeling happens before stale cleanup. Any label or cleanup failure returns a bounded degraded result; resume retries the entire idempotent repair without changing `LoopState`. Ordinary change-labelled issues are never selected or modified. Priority 1 plus cleanup keeps the sole current phase row inside the existing 50-row kanban window; the integration test seeds more than 50 ordinary lower-priority issues and verifies the exact label-only query still returns the current row.

### D10 — Projection isolation is scoped to the new publisher

Coordinator-free tiers may retain pre-existing coordinator detection and archetype-resolution imports. They SHALL NOT import or construct the new queue-projection module, register the adapter, or call `try_submit_work`, `try_reconcile_work_projection`, or the coordinator-only projection-label helpers. `runner.py` imports the projection module lazily only inside the `project-state` handler. Tests prove this with import/module spies and fail-fast call spies, not only by observing a lack of successful HTTP requests.

### D11 — Permanent identity rejection is bounded

The adapter validates the stricter projection change-id grammar before any bridge call. An Autopilot-valid identifier rejected by the projection grammar yields one bounded permanent-degradation result for that invocation; it is never retried within the same projection call. Later state writes remain authoritative and may report the same bounded degradation without queue traffic.

### Canonical write matrix

| Writer | Identity may change | Coordinated action after durable save |
|---|---:|---|
| `runner.py init` / in-process creation | yes | submit |
| `runner.py transition` / `_apply_transition` | yes | submit |
| `gate-check` / `gate-answer` / gate-session flush | sometimes | submit, including unchanged idempotent replay |
| `apply-outcome` | no | submit replay |
| `record-state-only-archetype` | no | submit replay |
| pending/stay/refusal paths | sometimes | submit |
| direct `enter_escalate` paths | yes; increment sequence once | submit |
| terminal memory append | no | submit replay |
| resume load | no | reconcile before gates/work |

No queue result, task status, label, or reconciliation response is ever an input to a state transition.
