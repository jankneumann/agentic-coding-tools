# Work-Queue Truth / Projection Contract

This guide defines the authority contract between an autopilot run's
**loop-state** and the coordinator **work queue**. It exists so future
implementers who wire autopilot dispatch onto the coordinator queue do so
without ever inverting the direction of truth.

## The two artifacts

| Artifact | Role | Location |
|----------|------|----------|
| **loop-state.json** | **Authoritative execution state** — the single source of truth for what phase a run is in, which iteration, which packages exist and their status, and the transition history. | `openspec/changes/<change-id>/loop-state.json` (schema: `LoopState` in `skills/autopilot/scripts/autopilot.py`, mirrors `convergence-state.schema.json`) |
| **work queue** | **Derived distribution / claim mechanism** — an optional projection of loop-state used to hand work to agents and claim it atomically. Every queue entry must be re-derivable from loop-state. | `agent-coordinator/src/work_queue.py` (`work_queue` plus `work_queue_projection_heads`; `/work/submit`, `/work/reconcile`, `/work/claim`, `/work/complete`) |

Loop-state is **versioned with the change** (it lives in the change directory
and travels with the branch), **survives coordinator outages** (it is a plain
JSON file on disk, not a row in the coordinator database), and **works in all
three execution tiers** — coordinated, local-parallel, and sequential. The work
queue exists only when a coordinator is available; it is never a prerequisite
for making progress.

This mirrors how [`coordinator-task-status-renderer`](../../skills/coordinator-task-status-renderer/SKILL.md)
treats coordinator state as an *informational projection* of the hand-authored
`tasks.md` checkboxes: the checkboxes are truth, the rendered status block is a
derived view that can be regenerated at any time and never feeds back into the
checkboxes. The same asymmetry holds here — loop-state is the checkboxes, the
queue is the rendered block.

> Autopilot now exposes an optional persist-first projection callback and a
> resume reconciliation callback. ri-08 does not register them for live phase
> mirroring; coordinated registration and latency guarantees remain ri-09 scope.

## Direction of truth

```
loop-state.json  ──(derive / project)──▶  work queue entries
      ▲                                          │
      └──────────  NEVER  ◀──────────────────────┘
```

Loop-state flows **into** the queue. The queue never flows back into
loop-state. Concretely: a run's current phase, iteration, and package status
are read from loop-state, and only from loop-state. A `get_work` / `/work/claim`
result is a *work item to execute*, never the record of what phase the run is
in.

## Enforcement rules for implementers

Any code that projects loop-state onto the queue MUST obey all three rules.

### (a) Idempotent queue submission

Public callers pass one complete `projection_key` with
`(change_id, phase, transition_sequence)`. `transition_sequence` is copied from
`LoopState.total_iterations`; phase-local `iteration` is never an identity. The
service alone materializes those reserved fields in `input_data`.

Migration `035_work_queue_projection.sql` enforces identity with a partial
unique expression index and serializes every keyed operation for one change
with `pg_advisory_xact_lock(hashtextextended(change_id, 0))`. The first keyed
submit establishes the full `(phase, transition_sequence)` head. Exact replay
returns the canonical task with `created=false`; a lower sequence returns
`stale_projection`, the same sequence with another phase returns
`projection_generation_mismatch`, and a higher sequence returns
`reconciliation_required`. Only reconciliation advances the head. Ordinary
submissions without `projection_key` continue to create independent rows.

### (b) Outbox ordering — persist first, enqueue second

Always **persist loop-state before enqueuing**. Save the authoritative state
transition to `loop-state.json`, then submit the derived queue entry. If the
process dies between the two, the truth is intact and the queue entry is simply
re-derived on resume (rule c). The reverse ordering — enqueue then persist — can
leave a claimed task with no authoritative state backing it, which is
unrecoverable.

### (c) On resume, re-derive from loop-state — never the reverse

When a run resumes, reconcile by reading loop-state and **re-deriving or
cancelling** queue entries to match it. Stale queue entries that do not
correspond to the current loop-state phase/iteration are cancelled; missing
entries are re-submitted (idempotently, per rule a). Never read the queue to
decide what phase the run is in, and never write loop-state from a claim
result.

## Tier applicability

**Claim atomicity is exercised only in the coordinated tier.** The
double-claim-prevention guarantee of `/work/claim` matters when multiple agents
draw from a shared queue. The **local-parallel** and **sequential** tiers run
**coordinator-free**: there is no queue, dispatch is driven directly from
loop-state by built-in Agent parallelism (local-parallel) or a single sequential
agent (sequential). In those tiers loop-state is not merely the source of truth —
it is the *only* execution-state artifact that exists.

## Invariant test

`skills/tests/coordination-bridge/test_work_queue_projection_invariant.py`
is an AST-enforced guard that fails if any skill source reads a run's phase,
iteration, or package status back out of a `work/claim` / `get_work` result. It
keeps the direction-of-truth arrow above from silently reversing.

It tracks *dataflow*, not spelling: it follows the name a claim result is bound
to (through nested subscripts and rebindings) and flags any read of an
authoritative field off it, whatever the variables are called. `change_id` is
deliberately exempt — a worker must be able to learn which change it is working
on in order to find the loop-state file to read the truth from.

It was previously a proximity regex over the literal symbols `current_phase` /
`loop_state` / `LoopState`. That only fired when the variable happened to carry
one of those names, so the realistic inversion — `claim = get_work()` then
`phase = claim["input_data"]["phase"]` — went undetected (issue #387). Both
verified false negatives are pinned as mutation cases in the test.

## Implemented projection interfaces

- HTTP: `POST /work/submit` accepts an optional `projection_key`;
  `POST /work/reconcile` requires it. Successful responses expose the canonical
  task ID, status, `created`, `deduplicated`, and sorted cancellation IDs.
  Authentication, policy, projection conflicts, and validation failures use
  RFC 7807 Problems.
- Direct and HTTP-proxy MCP expose `submit_work` and
  `reconcile_work_projection` with the same explicit key and discriminated
  no-raise failure envelopes.
- `coordination-cli work submit --projection-key <json>` and
  `coordination-cli work reconcile --projection-key <json>` map to the same
  service contract.
- `skills/coordination-bridge/scripts/coordination_bridge.py` provides optional
  submit/reconcile helpers. `skills/autopilot/scripts/autopilot.py` provides the
  persist-then-project helper and resume reconciliation injection seam.

## Failure recovery

A failed state write stops before projection. A failed projection never rewrites
the durable loop-state; resume re-derives the desired generation, atomically
cancels stale active rows, and ensures the current row exists. Completed,
failed, and cancelled current rows are treated as already satisfied. Queue
metadata is observability only and is never read back into `LoopState`.

## ri-09 boundary

ri-08 supplies atomic storage and optional composition seams. It does not
register a publisher for every live phase transition, modify kanban-viz, or
promise mirroring latency. ri-09 owns that coordinated runtime wiring.
