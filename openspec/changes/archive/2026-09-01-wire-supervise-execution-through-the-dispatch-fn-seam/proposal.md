# Change: wire-supervise-execution-through-the-dispatch-fn-seam

> Parent roadmap: `roadmap-supervisor-orchestration`
> Roadmap item: `ri-03`
> Inherited approvals: the operator's `$autopilot-roadmap` invocation approves discovery, the recommended direction, and the final plan for this item.

## Why

`/supervise` can intake and rank work, but it cannot yet execute an approved roadmap. The existing `autopilot-roadmap` callback is synchronous and advances one item through a second phase loop, so it neither fans out disjoint changes nor cleanly delegates each change's lifecycle to the existing Autopilot phase machine.

This change makes the supervisor the outcome-only host of roadmap execution: it selects safe ready batches, starts one background `/autopilot` sub-agent per change in a managed worktree, and feeds each structured result through the existing `dispatch_fn` seam without retaining child transcripts.

## What Changes

- Add opt-in `prepare_delegated_batch` and `apply_delegated_batch` entry points alongside unchanged `execute_roadmap()` behavior: Autopilot remains the sole per-change phase owner, while apply feeds each collected result through the existing synchronous `dispatch_fn` normalization seam exactly once.
- Enrich the `dispatch_fn(item_id, phase, context)` contract with the roadmap item's exact `change_id`, declared write scope, dispatch identity, execution mode, and parent worktree provenance while preserving the existing string and mapping result forms.
- Select a deterministic maximal ready batch only when a conservative tri-state scope classifier proves every pair disjoint across all packages, including integration and runtime-mirror writes; emit a schema-valid serial-indeterminate request otherwise.
- Persist every prepared generation and a generation-specific ack/go barrier before exposing it to the host. Pre-go stale claims are CAS-reclaimable; after go, only positive task-death evidence permits takeover, while unknown liveness becomes non-resumable quarantine rather than gate parking.
- Let the host invoke the selected batch concurrently as background `/autopilot <change-id>` agents, one managed worktree per change, while deterministic Python remains free of model SDK and provider calls.
- Reuse Autopilot's `phase_agent` / provider-dispatch outcome-and-handoff boundary; the supervisor keeps structured outcomes and handoff identifiers, never sub-agent transcripts.
- Represent pending-gate or paused Autopilot children as parked attempts, not failures, and define an authorized parked-to-launched continuation that reuses the same dispatch attempt/token under a new lease generation so ri-04 can resume it safely.
- Document and test the `supervise execute` host protocol, including resume, failure, worktree isolation, overlap serialization, and composition with router-supplied dispatch context.
- Add machine-readable request and result contracts for the supervisor-to-background-agent boundary.

No existing execution mode is removed. Callers that omit delegated-lifecycle options retain the current phase-by-phase behavior.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Isolation | Concurrent dispatched changes sharing a worktree or branch | 0; every dispatched change has a distinct verified managed worktree and branch | VALIDATE integration tests |
| Safety | Overlapping, ambiguous, or indeterminate scope pairs admitted to one batch | 0; only pairs classified `proven_disjoint` may fan out | VALIDATE unit/property tests |
| Context boundedness | Child transcript sentinels retained in the captured parent session or any durable output | 0 matches after a two-child host-protocol run | VALIDATE host-session integration fixture |
| Compatibility | Existing `execute_roadmap()` tests and legacy callback forms regressing | 0 regressions | CI `skills/tests/autopilot-roadmap` |
| Host-assisted execution | Direct LLM SDK or provider-network calls added under `skills/autopilot-roadmap/scripts/` or `skills/supervise/scripts/` | 0 | Existing and extended host-assisted invariant tests |
| Concurrency | Disjoint host task handles observed live before either wait | 2, while overlapping pairs remain serialized | VALIDATE integration test with synchronization barrier |

## Approaches Considered

### Approach 1: Delegated lifecycle plus scope-safe dispatch batches (Recommended)

Add explicit prepare/apply item-level orchestration around the existing synchronous `dispatch_fn` result seam. Deterministic code selects disjoint ready batches and persists typed envelopes; the host starts background agents, and each child runs the existing `/autopilot` phase machine.

**Pros**

- Keeps one phase-machine owner: Autopilot remains authoritative for `loop-state.json`.
- Preserves the host-assisted invariant and existing provider/router decisions.
- Enables real fan-out while failing closed when scopes cannot prove independence.
- Adds behavior without changing legacy callers.

**Cons**

- Adds an opt-in execution mode and item-level scheduling state to the roadmap orchestrator.
- Requires explicit request/result contracts and resume tests.

**Effort**: L, decomposed into M-sized work packages.

### Approach 2: Map every roadmap phase directly to a background lifecycle skill

Keep the current roadmap phase loop and have the supervisor dispatch `/plan-feature`, `/implement-feature`, review, and validation separately for each callback.

**Pros**

- Smallest change to `execute_roadmap()`.
- Existing phase names remain directly observable.

**Cons**

- Creates a second lifecycle owner beside Autopilot and risks duplicate or contradictory phase transitions.
- Reimplements outcome, gate, and retry behavior already present in `phase_agent` and `provider_dispatch`.
- Still needs a separate concurrency mechanism across items.

**Effort**: M.

### Approach 3: Put dispatch into a resident supervisor service

Introduce a coordinator daemon or API that launches agents and owns their handles independently of the host session.

**Pros**

- Natural process-level concurrency and persistent handles.
- Supervisor sessions could disconnect while work continues.

**Cons**

- Violates the roadmap's "promote the role, don't build a runtime" principle.
- Adds a second decision-maker and a direct execution/network boundary.
- Expands scope into always-on scheduling owned by another roadmap.

**Effort**: L.

### Recommended

Approach 1 is recommended because it is the only option that satisfies concurrent execution without duplicating Autopilot's phase machine or creating a resident supervisor runtime. Its extra scheduling state is bounded, deterministic, and testable; the conservative fallback to sequential execution makes missing scope evidence safe.

### Selected Approach

**Approach 1: Delegated lifecycle plus scope-safe dispatch batches.** Selected under the inherited roadmap approval. The implementation must compose with `make-the-orchestrator-obey-the-router`: router/vendor fields remain additive context owned by that change, and this change must preserve unknown context keys rather than select a vendor itself.

## Impact

### Affected capabilities

- `roadmap-orchestration` — delegated item lifecycle, scope-safe ready batches, result/resume semantics.
- `supervise` — approved-roadmap `execute` behavior and outcome-only host protocol.
- `skill-workflow` — background sub-agent isolation and transcript boundary for supervised execution.

### Major code and documentation surfaces

- `skills/autopilot-roadmap/scripts/orchestrator.py`
- `skills/autopilot-roadmap/SKILL.md`
- `skills/supervise/SKILL.md`
- `skills/roadmap-runtime/scripts/dispatch_scheduler.py` (new neutral scope/batch helper)
- `skills/supervise/scripts/execution.py` (new host prepare/launch/resume/apply adapter)
- `skills/roadmap-runtime/scripts/models.py` and `checkpoint.py`
- `openspec/schemas/checkpoint.schema.json` and its installed-asset source
- `skills/roadmap-runtime/scripts/scope_overlap.py` (reuse; modify only if a missing fail-closed primitive is proven)
- `skills/tests/autopilot-roadmap/`
- `skills/tests/supervise/`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/contracts/`

Architecture layers: Execution (background Autopilot agents and worktrees) and Coordination (roadmap scheduling/checkpoints). Trust and Governance continue to be consumed through existing router, handoff, and approval-gate contracts and are not reimplemented here.

### Dependencies and conflicts

- Builds on completed ri-01 (read-only frontier supervisor), ri-02 (`/supervise` host role), and ri-05 (supervisor handoff record).
- `make-the-orchestrator-obey-the-router` overlaps `orchestrator.py`; this change preserves additive dispatch context and must rebase/sequence cleanly rather than introduce vendor selection.
- `add-supervisor-candidate-work-digest` overlaps `skills/supervise/SKILL.md` and supervise tests; isolate commits and rebase before integration.
- Committed architecture artifacts were stale and could not be refreshed for this repository layout, so no architecture-derived parallel-zone claim is used as authority.

## Out of Scope

- Gate posture and approval routing (ri-04).
- Queue mirroring, idempotent outbox submission, and kanban projection (ri-08/ri-09).
- Vendor or model selection, cost policy, and router implementation.
- An always-on daemon, notification channels, or unattended merge-policy changes.
- Replacing Autopilot's existing `phase_agent` or provider-dispatch protocol.
