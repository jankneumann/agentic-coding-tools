# Tasks: Mirror Autopilot Phase State into the Work Queue

## Phase 1 — RED contract tests

- [x] 1.1 Write adapter RED tests for exact projection identity, stricter-id rejection, bounded allowlisted payload, three successive generations using the exact nested HTTP-409 bridge envelope while `projection_generation_mismatch` remains degraded, plus direct ESCALATE sequence advancement, direct reconcile mode, `task_type=issue`/priority-1 board visibility and unfiltered-claim exclusion, coordinator-only canonical-row label correlation, interrupted cleanup/idempotency, non-success envelopes, and response non-authority.
- [x] 1.2 Write host-driven CLI RED tests for canonical `init` and `transition` writers plus explicit `project-state --mode submit|reconcile`; cover every runner state-mutating command and gate exit 0/3/4, proving save-before-project, save-failure suppression, and reconcile-before-gate/work ordering.
- [x] 1.3 Write import/module and fail-fast call-spy regressions proving local-parallel/sequential execution neither imports the new projection module nor constructs/registers it nor calls submit, reconcile, or coordinator-only projection-label helpers; exclude pre-existing detection/archetype bridge use.

## Phase 2 — Coordinated adapter and registration

- [x] 2.1 Implement the shared LoopState-to-bridge projection adapter with explicit connection/configuration injection, submit-to-reconcile head advancement, `task_type=issue`, and exact adapter-owned labels passed through the coordinator-only work-queue bridge regardless of GitHub issue-backend configuration.
- [x] 2.2 Make every direct `enter_escalate` phase change increment `total_iterations` once; add `runner.py init`, `runner.py transition`, and the read-only `project-state` boundary; register the adapter explicitly in coordinated in-process and host-driven execution without changing the state-machine default or `apply-outcome` semantics.
- [x] 2.3 Update the Autopilot skill protocol to use canonical CLI writers, perform submit after every durably successful state mutation (including gate exit 4 parks), suppress projection after failed saves, and reconcile before resume gate handling/work.

- [x] 2.4 Add migration `037_autopilot_phase_projection_visibility.sql` to exclude `task_type=issue` from every claim and emit a change-scoped event when adapter-owned projection labels change; derive change ID from NEW labels with OLD-label fallback on removal, and make `event_stream.py` convert it to a fresh bounded snapshot for connected clients.

- [x] 2.5 Bring `openspec/contracts/agent-coordinator/openapi/work-queue.yaml` up to revision 2 by declaring `projection_key`, `/work/reconcile`, and typed 403/409/422 problem responses used by the adapter.

- [x] 2.6 Add migration `038_atomic_projection_labels.sql` so submit/reconcile applies canonical labels and clears owned stale labels while holding the per-change advisory transaction; exclude cancelled rows from implicit issue-list status selection as defense in depth, and declare the optional exact `projection_labels` request in the runtime/OpenAPI contract.
- [x] 2.7 Add migration `039_projection_integrity_and_insert_events.sql` for first-insert refresh, replay repair, fail-closed non-issue collisions, and owned terminal-row reactivation; add executable retry-idempotent ESCALATE recovery and flush auto `escalate_resume` before continuing.

## Phase 3 — Behavioral and crash recovery proof

- [x] 3.1 Prove canonical `runner.py` writers and file-derived projection at the host boundary, then drive the full FastAPI/service/PostgreSQL path through three successive live generations, head advancement, idempotent replay, stale rejection/cancellation, concurrent publisher serialization, GitHub-backend override resistance, the 100-row bridge bound, unfiltered claim exclusion, and exactly one active current board-visible projection row.
- [x] 3.2 Simulate termination after loop-state save but before submit; resume and prove reconciliation derives solely from the durable file and leaves that file byte-for-byte unchanged.
- [x] 3.3 Verify an already connected real EventBus SSE client receives both the first canonical insert and stale-to-current reconciliation as current-only snapshots, while label-only polling exposes the priority-1 current phase within 5 seconds after more than 50 ordinary issues.

## Phase 4 — Integration and validation

- [x] 4.1 Update the work-queue truth/projection guide and Autopilot documentation with registration, degradation, and latency behavior.
- [x] 4.2 Synchronize runtime skill mirrors and make `install.sh --check` fail on byte-level installed-payload drift.
- [x] 4.3 Run focused Autopilot/bridge/coordinator/kanban tests, real PostgreSQL projection tests when available, Ruff, the AST truth-direction and projection-import invariants, strict OpenSpec, context-drift, and scope validation.
