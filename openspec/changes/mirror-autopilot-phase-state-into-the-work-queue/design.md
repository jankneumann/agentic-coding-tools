# Design: Coordinated Autopilot Phase Projection

## Context

`autopilot.run_loop` already persists before invoking an optional `queue_projection_fn`, and invokes that callback in `reconcile` mode after loading existing state. The coordination bridge already exposes no-raise keyed submit and reconcile helpers. The missing behavior is registration at the real coordinated host boundary, including the CLI-driven protocol used by the Autopilot skill.

## Decisions

### D1 — One adapter derives one exact projection

Add a small Autopilot-side adapter whose only input is `LoopState` plus explicit coordinator connection settings. It derives `projection_key={change_id, phase=current_phase, transition_sequence=total_iterations}` and the bounded payload in D6. Submit mode uses the head-advance algorithm in D7; reconcile mode directly repairs from durable state. Both mutations pass D9 exact owned labels into the coordinator transaction. The adapter accepts no identity overrides and never returns queue values to the state machine.

### D2 — Registration is explicit at the execution-tier boundary

The state machine keeps `queue_projection_fn=None` by default. Only an explicitly selected coordinated host constructs and injects the adapter; local-parallel and sequential hosts follow D10. The host CLI exposes the canonical `init` and `transition` writers from D8 plus `project-state --mode submit|reconcile`. `project-state` requires explicit coordinator connection settings, loads the just-written state itself, and never changes state. No environment-only inference silently enables queue traffic.

### D3 — State persistence remains authoritative

Every coordinated loop-state write follows the D8 write matrix: durable save first, then projection, including idempotent replay when identity is unchanged. A state-save failure suppresses projection. A projection exception or bridge `{status: skipped|failed}` envelope is reported as degradation but never rolls back the saved phase. On resume, the adapter re-derives the desired tuple from the loaded file; it never reads a claimed/current queue row to mutate state.

### D4 — Host-driven and in-process flows share serialization

The in-process `run_loop` continues using `persist_and_project`. The CLI boundary calls `project-state` and a shared serializer/adapter rather than reproducing projection-key construction in `SKILL.md`. `apply-outcome` remains phase-state bookkeeping only and does not silently enable coordinator traffic. If host-side bookkeeping fails, the explicit `runner.py escalate` writer durably parks the retained handoff; unsupported logical `transition` edges do the same automatically and exit zero so the parked generation is projected. The skill protocol names the exact post-write and resume-reconcile calls, so supervise-dispatched runs inherit the same behavior automatically.

### D5 — Existing kanban data path is the proof surface

No frontend changes are planned. Migration `037_autopilot_phase_projection_visibility.sql` emits label-update events, and migration 039 emits the corresponding first-insert event so a client connected before the canonical generation receives a bounded fresh snapshot. `event_stream.py` converts either event to SSE snapshot replacement. Migrations 038 and 039 keep cancellation, exact label replacement, durable ownership checks, and terminal-row reactivation inside the per-change transaction; implicit issue-list reads exclude cancelled rows. Live tests cover first insert, reconciliation, three generations, direct ESCALATE advancement, more than 50 ordinary issues, and a crash/resume derived only from durable state.

### D6 — Projection payloads are bounded and non-authoritative

Input metadata is allowlisted to change path, execution tier, and projection provenance; reserved identity fields appear only in `projection_key`. Descriptions and paths use existing bridge/service bounds. The adapter-owned row labels are exactly `change:<change_id>` and `projection:autopilot-phase`; D9 makes their transactional replacement set-idempotent without touching ordinary issues. Logs expose status/reason/task IDs but not credentials, child transcripts, or queue payload echo.

## Failure Matrix

| Failure | Durable truth | Queue | Recovery |
|---|---|---|---|
| save fails | old loop-state | unchanged | abort before projection |
| process dies after save | new loop-state | old/missing | resume reconciliation |
| bridge/coordinator unavailable | new loop-state | old/missing | degraded result; next resume reconciles |
| projection transaction fails | new loop-state | prior committed projection | degraded result; resume reconciles the complete row/label mutation |
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

Add `runner.py init`, `runner.py transition --outcome <outcome>`, and `runner.py escalate --reason <reason>`. Init persists invocation force/review flags on first creation; transition and escalate replay after DONE are byte-preserving no-ops. Unsupported logical transitions and host-side apply failures durably enter ESCALATE from the authoritative durable phase; retries already parked retain the original generation, resume phase, reason, and phase-start time. Successful apply-outcome bookkeeping best-effort replays the unchanged generation. Both automatic and console-approved `escalate_resume` decisions apply and persist the canonical `resolved` edge before host projection; exits 1 and 2 suppress projection. Resume reconciliation still runs before gates or phase work.

`run_loop` currently has no production caller; as a library contract it accepts an explicitly injected adapter and routes every `save_state` site through `persist_and_project`, including initial creation, gate-session flushes, pending/stay paths, transition refusals, ESCALATE writes, and terminal memory bookkeeping. `_GateSession` gains an optional projection callback defaulting to None: only `run_loop` passes it, while `runner.py` leaves it unset because the CLI host projects after the command returns. Re-projecting an unchanged identity is an intentional idempotent replay. A failed save never invokes projection.

### D9 — Board-visible rows and label repair

Projection rows use `task_type="issue"` and priority 1. They are visible to the existing issue-only `/issues/list` path. Migration 037 adds the missing `task_type <> "issue"` predicate to `claim_task`, aligning enforced claim behavior with the existing issue-service contract and making projection and all ordinary issue rows unclaimable even when `task_types` is absent. Their bounded, adapter-owned label set is exactly `change:<change_id>` plus `projection:autopilot-phase`.

Migration 038 extends submit/reconcile with an optional exact `projection_labels` argument. While holding the existing per-change advisory transaction, the database ensures the canonical generation, applies that exact set to its row, cancels stale active generations, and clears the owned labels from every noncanonical row. This closes the client-side N/N+1 repair race: a delayed older publisher cannot remove the labels of a newer generation after the serialization lock is released. The adapter passes labels only through coordinator-only work-queue helpers, so GitHub issue-backend configuration cannot redirect the mutation. Ordinary change-labelled issues are never selected or modified. Implicit issue-list reads exclude cancelled rows as a defense-in-depth board contract, while an explicit all-status query remains available. Priority 1 plus atomic cleanup keeps the sole current phase row inside the existing 50-row kanban window; the integration test seeds more than 50 ordinary lower-priority issues and verifies the exact label-only query still returns the current row.

Migration 039 closes the remaining owned-projection integrity cases while preserving unlabelled legacy semantics outside labelled namespaces. Same-generation submit clears every noncanonical registry-owned label; a database-owned UUID registry is the sole ownership authority and distinguishes canonical projection rows from any ordinary row at any tuple; mutable payload fields and labels cannot confer ownership; every unowned reserved-label collision fails before head advancement, cancellation, or relabelling in either mode; the labelled projection path restricts cancellation, label cleanup, and reactivation to registry-owned rows; and the legacy `p_projection_labels IS NULL` path preserves its historical tuple-cancellation contract only when the change has no owned projection row. Once an owned row exists, unlabelled submit/reconcile returns `projection_mode_mismatch` without mutation. Symmetrically, labelled submit/reconcile refuses every change namespace containing a complete unowned projection tuple with `projection_key_collision` before head or row mutation. Active canonical rows preserve their lifecycle state, and an owned canonical row made terminal out of band is restored to pending with lifecycle fields cleared and emits a projection refresh event. The authored OpenAPI and Pydantic request models both declare the heterogeneous ordered pair, canonical change-label pattern and 135-character bound, fixed second label, and conditional projection-key/issue requirements.

Upgrade rule: migration 039 performs no automatic ownership seeding because every pre-039 payload and label signal is client-mutable. All pre-registry rows, including legitimate migration-038 projections, remain unowned and fail closed with `projection_key_collision` until a database administrator verifies provenance out of band and inserts the UUID into `work_queue_projection_ownership`. Before either labelled submit or reconcile mutates a head or row, it scans the change for any complete unowned keyed projection row, while either request mode separately scans for an unowned row carrying the reserved projection label together with the matching payload change ID or exact change label. This preflight applies even when the requested generation is newer: advancing a generation alone is not a repair because an unowned labelled legacy row cannot be safely relabelled or cancelled. Runtime functions never infer or grant ownership from work-queue fields.

Post-upgrade rule: the reserved projection marker is database-owned rather than cosmetic. Projection RPCs insert without labels, register the new UUID, then apply the exact pair in the same transaction. A trigger rejects every insert or label update that supplies `projection:autopilot-phase` before registry ownership exists. Ordinary issue create/update also rejects the marker before persistence. Ordinary issue update and close go through one row-locking RPC that rejects registry-owned rows before applying an allowlisted patch, so no HTTP or service-layer race can mutate a canonical projection. Attempts across either boundary return HTTP 403 from the issue API and leave the row unchanged.

### D10 — Projection isolation is scoped to the new publisher

Coordinator-free tiers may retain pre-existing coordinator detection and archetype-resolution imports. They SHALL NOT import or construct the new queue-projection module, register the adapter, or call `try_submit_work`, `try_reconcile_work_projection`, or the coordinator-only projection-label helpers. `runner.py` imports the projection module lazily only inside the `project-state` handler. Tests prove this with import/module spies and fail-fast call spies, not only by observing a lack of successful HTTP requests.

### D11 — Permanent identity rejection is bounded

The adapter validates the stricter projection change-id grammar before any bridge call. An Autopilot-valid identifier rejected by the projection grammar yields one bounded permanent-degradation result for that invocation; it is never retried within the same projection call. Later state writes remain authoritative and may report the same bounded degradation without queue traffic.

### D12 — Projection publication is an elevated, change-scoped operation

HTTP requests carrying `projection_key`, local service submissions carrying a projection key, and every reconcile request authorize the distinct `publish_work_projection` operation before database mutation. The authorization resource is the exact `projection_key.change_id`, and the audit context records that change ID plus projection mode. Trust-level-2 principals that may submit ordinary work cannot publish or repair projections; only trust-level-3 coordinator publishers receive the operation through the native policy and synced capability profile. Local MCP projection helpers remain coordinator-only and all configured local harness publishers are trust level 3. Native and Cedar policy modes resolve omitted trust through the shared fail-closed resolver; resolution failure on submit or reconcile never reaches the mutating RPC.

Direct MCP submit/reconcile and the MCP HTTP proxy expose and forward the same optional exact `projection_labels` pair as HTTP and the service. An omitted pair retains the generic legacy keyed-projection contract but cannot cross into a registry-owned labelled change namespace.

The in-process convergence entry point resolves its vendor panel from the reviewed worktree before consulting a running coordinator, matching direct review dispatch. This prevents a stale shared-checkout roster from silently changing the configured harness set for an active feature review.

### Canonical write matrix

| Writer | Identity may change | Coordinated action after durable save |
|---|---:|---|
| `runner.py init` / in-process creation | yes | submit |
| `runner.py escalate` / failed logical transition | yes once | submit parked ESCALATE generation |
| `runner.py transition` / `_apply_transition` | yes | submit |
| `gate-check` / `gate-answer` / gate-session flush | sometimes | submit, including unchanged idempotent replay |
| `apply-outcome` | no | submit replay |
| `record-state-only-archetype` | no | submit replay |
| pending/stay/refusal paths | sometimes | submit |
| direct `enter_escalate` paths | yes; increment sequence once | submit |
| terminal memory append | no | submit replay |
| resume load | no | reconcile before gates/work |

No queue result, task status, label, or reconciliation response is ever an input to a state transition.
