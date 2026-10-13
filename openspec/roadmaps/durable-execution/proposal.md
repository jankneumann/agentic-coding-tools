# Durable Execution Adoptions (from Pi Durable)

## Motivation

Pi Durable (Josh Rosen, "Pi Durable vs. OpenCode: An Architectural Comparison", 2026-10)
stores *execution state* rather than only *session state*: model generations, tool
calls, compaction, and application work are durable tasks, a scheduler drives them
from storage, documents commit atomically with the conversation, and tools declare
whether they are safe to replay. A comparison against this repository found that the
metaharness already applies most of these ideas, but **one layer up**. The durable unit here is the phase, the change, the
roadmap item, and the supervised dispatch: `loop-state.json` and `checkpoint.json`
are authoritative execution state (`docs/guides/state-artifacts.md`), the coordinator
queue is a persist-first, idempotent projection (`docs/guides/work-queue-truth-projection.md`),
and the supervisor already refuses to infer death from a missing heartbeat and never
replays an applied effect (`skills/supervise/SKILL.md`, `application_journal`).

Below that layer, every vendor session is opaque and non-durable. Four concrete gaps follow:

1. **Phases restart from scratch.** `skills/autopilot/scripts/phase_agent.py` (design D8)
   retries a crashed IMPLEMENT / IMPL_REVIEW / VALIDATE sub-agent up to three times with
   the *same incoming* PhaseRecord. A retry recovers only what happened to land on disk,
   with no record of which steps finished. The atomic-harness proposal names long-running
   phases as the place "where our `loop-state.json` resume is weakest."
2. **Irreversible actions inside a phase have no ledger.** `git push`, PR creation,
   merges, deploys, coordinator mutations, and external notifications run inside skill
   scripts and vendor turns with no record of "requested / started / finished". A retry
   after a crash cannot tell whether the PR or deploy already exists. The supervisor's
   `application_journal` solves this for dispatch application only.
3. **Fork semantics are implicit.** Worktrees and branches are forks, and sync-point skills
   decide when a fork sees newer state, but no artifact declares whether it should carry
   the fork-point value, track the latest value from main, or start fresh. Pi makes this a
   per-document declaration. Here it is convention, and violations only show up as merge
   conflicts or stale reads.
4. **Cancellation does not cascade.** `/refine-roadmap` refuses to supersede in-progress or
   checkpoint-referenced items, and there is no operation that stops an item's change, its
   work packages, its queue projection rows, and its live sub-agents together. Stopping
   in-flight work today is a manual, multi-artifact operation.

Success: a crashed phase resumes from its last durable step instead of from scratch; no
irreversible action is ever repeated silently after an interruption; every durable
artifact declares its fork policy and a check enforces it; an operator can abort a
roadmap item and every piece of work it owns stops, is recorded, and is left resumable
or terminal (never half-applied); and a durable intra-phase executor (Atomic / Pi
Durable) can be plugged in without creating a second source of truth.

## Capabilities

### Capability: Effects journal with replay-safety declarations

A generalized, append-only **effects journal** for irreversible or externally visible
actions taken by skill scripts: push, PR create/update/merge, deploy/teardown, issue and
comment posting, coordinator mutations that are not already idempotency-keyed, and
external notifications. Each effect is written as `requested` **before** it executes,
moves to `started` and then to `completed` (with its observable result, e.g. PR URL or
commit SHA) or `failed`, and carries a stable idempotency key derived from
`(change_id, phase, transition_sequence, effect_kind, target, operation_digest)`.
`operation_digest` is a deterministic digest of the effect's intended payload (the
commit SHA being pushed, a comment body, a PR's head/base), so a retry of the same
effect reuses its key while a second, distinct effect on the same target (another
comment on one issue, a later push to one ref) gets its own.

Each effect kind declares a **replay policy**: `replayable` (safe to re-run, e.g.
an idempotent upsert), `verify_then_skip` (probe the world for the result before re-running,
e.g. "does a PR for this head branch exist?"), or `never_replay` (an interrupted
`started` entry is quarantined and escalated, as the supervisor does for an `unknown`
dispatch). The journal lives with the change (`openspec/changes/<change-id>/effects.jsonl`)
so it travels with the branch and survives coordinator outages. An optional coordinator
projection follows the persist-first rule from the work-queue contract. The supervisor's
`application_journal` is documented as the first, specialized instance of this pattern
rather than rewritten.

**Acceptance Outcomes:**
- Two distinct effects of the same kind on the same target within one phase receive distinct keys, while a retry of the same effect reuses its key.
- A shared helper (`skills/shared/effects_journal.py` or equivalent) exposes `begin`, `complete`, `fail`, and `resolve_interrupted` and is used by `/cleanup-feature`, `/merge-pull-requests`, `/validate-feature` (deploy/teardown), and the autopilot SUBMIT_PR step.
- A fault-injection test that kills the process between `started` and `completed` for each policy shows: `replayable` re-runs once; `verify_then_skip` finds the existing PR/commit and records `completed` without a second side effect; `never_replay` parks the change with a named escalation and performs no action.
- A guard test fails if a listed effect-producing command (`gh pr create`, `git push`, merge APIs, deploy entry points) is called from a skill script outside an effects-journal wrapper.
- `docs/guides/state-artifacts.md` lists the effects journal with holder, writer, authority, and missing/stale behavior, and states that it is authoritative for "did this effect happen?" and for nothing else.

### Capability: Phase progress checkpoints for resumable phases

Replace "retry from scratch with the same incoming PhaseRecord" with **resume from
the last durable step**. A phase sub-agent appends progress checkpoints to a phase-scoped
journal (`openspec/changes/<change-id>/phase-progress/<phase>-<transition_sequence>.jsonl`):
completed work-package tasks, review rounds finished, validation phases passed, and a rolling
bounded summary (the in-progress draft of the PhaseRecord). On retry, `phase_agent.py` hands
the new sub-agent the latest checkpoint and draft summary in addition to the incoming
PhaseRecord, so it can skip completed steps instead of re-deriving them from disk.

This is the metaharness counterpart to Pi's early, background compaction: the
phase-end PhaseRecord becomes the finalized version of a summary that was written
progressively, rather than a summary produced all at once at the end. The driver contract
`(outcome, handoff_id)` is unchanged. Progress checkpoints are advisory context for the
phase that wrote them and never replace `loop-state.json` as the record of which phase
the run is in.

**Acceptance Outcomes:**
- A phase interrupted after N of M checkpointed steps resumes and performs only steps N+1..M; a test with a recording runner verifies that completed steps are not re-dispatched.
- Resume consults the effects journal for any step whose checkpoint is missing but whose effect is `started` or `completed`, so a checkpoint gap never causes an irreversible action to repeat.
- Retry budgets (D8, three attempts) count *attempts without progress*; an attempt that adds at least one checkpoint does not consume budget, with a hard ceiling to prevent unbounded loops.
- The finalized PhaseRecord for a resumed phase is the same shape as a single-attempt PhaseRecord and passes existing `session-log` validation.
- Missing or corrupt progress journals degrade to today's retry-from-scratch behavior and are reported, never repaired from advisory content.

### Capability: Declared per-artifact fork policies

Give every durable artifact class a declared **fork policy** that says what a new branch
or worktree sees: `fork_point` (carry the value at fork time and diverge, e.g. proposal,
tasks, specs), `latest` (always read the main-line / single-writer value, never a forked
copy, e.g. roadmap `checkpoint.json`, the supervisor cycle ledger, generated
`docs/decisions/`), or `fresh` (start empty in the fork, e.g. `loop-state.json` for a new
run, phase-progress journals, effects journals for a new change). Policies are declared
in one registry next to the `state-artifacts.md` inventory, and each owning writer
enforces its artifact's policy at read time.

**Acceptance Outcomes:**
- Every artifact class in `docs/guides/state-artifacts.md` (plus the effects journal and phase-progress journal) carries a fork policy in a machine-readable registry.
- A check, run in CI and by `/expedite`, flags a `latest`-policy artifact modified on a feature branch outside its declared single writer, and a `fresh`-policy artifact copied into a new change from another change.
- Worktree setup for a work package materializes `fresh` artifacts empty and does not copy `latest` artifacts into the package branch; a test covers each policy.
- Sync-point skills (`/merge-pull-requests`, `/update-specs`, `/cleanup-feature`) reference the registry instead of restating per-artifact rules locally.

### Capability: Cascading abort over the ownership graph

A first-class **abort** operation over the existing ownership graph
(roadmap → item → change → work packages → supervised dispatches / phase sub-agents →
queue projection rows → effects). Aborting a node records the intent durably first
(in the owning canonical artifact: checkpoint for items, loop-state for changes), then
propagates to owned nodes: live sub-agents are interrupted at their next checkpoint
boundary; pending queue projections are cancelled through the existing reconcile path;
`requested` effects are cancelled; `started` effects are resolved by their replay policy,
never abandoned silently; and leases are released only where death or completion is
proven, keeping the supervisor's `unknown` → quarantine rule.

Abort leaves each node either **terminal** (`aborted`, with reason) or **parked and
resumable**, and the operator chooses which. Work that is explicitly marked
`detached` (the counterpart of Pi's background work that outlives its parent) is
skipped by the cascade and reported. This closes the gap where `/refine-roadmap`
correctly refuses to supersede in-progress items but nothing can stop them.

**Acceptance Outcomes:**
- `abort <roadmap-id>:<item-id>` (and the change-level form) cancels every owned queue row, interrupts or quarantines every owned dispatch, and writes `aborted` state to the owning canonical artifact; a recorded integration test asserts the full set.
- Aborting during a `started` `never_replay` effect leaves that effect quarantined and the node parked, not `aborted`, and names the effect in the escalation.
- Abort is idempotent: re-running it on a partially aborted tree completes the remaining nodes and changes nothing already terminal.
- Abort works in all three tiers; in coordinator-free tiers it operates on loop-state and local sub-agent handles only.
- After an abort, `/refine-roadmap` can supersede the aborted item without a manual checkpoint edit.

### Capability: Durable intra-phase executor boundary (Atomic / Pi Durable)

Define and enforce the authority boundary for plugging a durable workflow engine
(Atomic, a pi fork, or Pi Durable itself) in as the executor *inside* a phase. The
engine's task ledger is authoritative for intra-phase progress (which generations and
tool calls completed). `loop-state.json` stays authoritative for which phase the run
is in, and the effects journal stays authoritative for irreversible repository and
external actions. The adapter maps engine run events onto phase progress checkpoints
and engine tool-replay declarations onto effects-journal policies, so a durable
executor and an opaque vendor CLI produce the same metaharness-visible artifacts.

Builds on, and does not duplicate, the in-flight `add-atomic-harness` change (its
Level-2 `workflow_dispatch.py` pilot), which this roadmap adopts as its own item so the
dependency is a real scheduling edge. Scope here is the contract and its enforcement
in `phase_agent.py`, and promoting the pilot from `fix-scrub` to an opt-in IMPLEMENT /
VALIDATE executor.

**Acceptance Outcomes:**
- `state-artifacts.md` gains a row for the executor ledger whose authority is limited to intra-phase progress; the rehydration order states that it is consulted only after `loop-state.json` identifies the phase.
- `phase_agent.py` accepts a durable executor behind the same `(outcome, handoff_id)` contract; resuming an interrupted Atomic-backed phase continues the engine run (same `runId`) instead of starting a new attempt.
- An engine tool marked non-replayable maps to a `never_replay` effect; a recorded-fixture test shows that an interrupted run does not repeat it.
- The AST guard in `test_work_queue_projection_invariant.py` (or a sibling) also fails if a phase or package status is read back from the executor ledger.
- Executor selection is opt-in per phase and per change; with it disabled, behavior is identical to today's.

## Constraints

- The system must preserve the direction-of-truth rules: canonical artifacts (`loop-state.json`, `checkpoint.json`) are persisted first, and every projection, journal mirror, or executor ledger is derived or scoped and never written back into canonical state.
- The system must keep working with the coordinator unreachable: every new artifact shall live on disk with the change or roadmap, and any coordinator copy is an optional projection.
- The system must work in all three execution tiers (coordinated, local-parallel, sequential), and in cloud-harness environments where worktree operations short-circuit.
- The system shall not assume ownership of a vendor's inner loop: opaque vendor CLIs (Claude Code, Codex, Gemini, pi) must remain first-class executors. Durable intra-phase execution is opt-in.
- The system must never repeat a `never_replay` effect automatically, and must never infer death from an absent or expired heartbeat. Uncertainty resolves to quarantine plus escalation.
- Each new authority must be added to `docs/guides/state-artifacts.md` in the same change that introduces it, with holder, writer, authority, consumers, and missing/stale behavior.
- New state files shall be deterministic (no wall-clock-dependent identity) and must not change the supervisor cycle fingerprint when written as supervisor-output-only artifacts.
- Durable artifacts must stay small and human-reviewable in PRs: journals are bounded, and transcripts are never stored.

## Phases

### Phase 1: Safety foundations

- Capability: Effects journal with replay-safety declarations
- Capability: Declared per-artifact fork policies

### Phase 2: Resumability and control

- Capability: Phase progress checkpoints for resumable phases (depends on the effects journal)
- Capability: Cascading abort over the ownership graph (depends on the effects journal)

### Phase 3: Durable executor integration

- Adopted change: `add-atomic-harness` (no dependencies; can run in parallel with Phase 1)
- Capability: Durable intra-phase executor boundary (depends on phase progress checkpoints, the effects journal, and `add-atomic-harness`)

## Out of Scope

- Replacing the metaharness's phase-level state machine with a fine-grained task scheduler, or making generations and tool calls of opaque vendor CLIs durable. That belongs to the executor, not the metaharness.
- Background or speculative context compaction inside a vendor session; the metaharness does not control vendor context windows.
- Preemptive scheduling of agent work (the operating-system analogy in the source article).
- A single atomic transaction spanning git and the coordinator database. Atomicity continues to come from persist-first ordering plus idempotent re-derivation.
- The Symphony dispatcher daemon, retry queue, and tracker reconciliation (`openspec/roadmaps/symphony/`); cascading abort shall integrate with them when they land, not reimplement them.
- Re-planning `add-atomic-harness`. The roadmap adopts it as an item and owns its execution and scheduling, but its proposal, design, and tasks stay as authored in that change.
