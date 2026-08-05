# Supervisor Orchestration: A Single Conversational Counterpart for the Human

## Context and Goals

The repository's orchestration stack is complete below the human: `/plan-roadmap`
decomposes proposals into a change DAG, `/autopilot-roadmap` iterates items through
an injected `dispatch_fn`, `/autopilot` drives each change's phase machine as the
sole writer of `loop-state.json` transitions, and per-phase archetypes route
sub-agents to vendor/model/thinking tiers. What is missing is the layer *above*:
a single, persistent, conversational counterpart the human talks to — the role
Steve Yegge's Gas Town calls the **Mayor** and kunchenguid/firstmate calls the
**First Mate**. Today the human is the supervisor: they invoke each skill, carry
findings from discovery skills back into proposals by hand, and discover parked
escalations only when a later session happens to load a handoff document.

This proposal adds the supervisor as a **promoted role, not a new component**: a
frontier-tier archetype plus a conversational skill that the host harness session
plays, filling the injection seams the stack already exposes (`run_loop`'s phase
callbacks, `execute_roadmap`'s `dispatch_fn`, `ApprovalGate.evaluate`). It also
lands the state contracts and artifact standardization that make a supervisor
trustworthy: an explicit truth/projection contract between `loop-state.json` and
the coordinator work queue, and a single candidate-work schema so the discovery
back-edge (bug-scrub, improve-harness, explore-feature) closes into the roadmap
without a human courier.

Relationship to `docs/proposals/always-on-agent-automation.md`: that proposal
builds the autonomic layer — trust posture (ri-04, delivered), approval gate
service (ri-05, delivered), gate encoding (ri-06, candidate), dispatcher daemon
(ri-08, candidate), scheduled discovery and findings-to-issues (Phase 6). This
proposal builds the *cognitive* layer that consumes those bricks conversationally.
The two compose: the daemon rehydrates supervisor sessions on events; it never
becomes a second decision-maker.

## Guiding Principles

- **Promote the role, don't build a runtime.** The supervisor is the host harness
  session playing an archetype, per the host-assisted invariant
  (`skills/autopilot-roadmap/SKILL.md`: skills make no direct LLM API calls).
  Python remains deterministic helpers; judgment stays in the session.
- **Git is truth; the database is a projection.** `loop-state.json`, roadmap
  `checkpoint.json`, and handoffs are authoritative execution state, versioned
  with the change. Coordinator state (work queue, status) is derived, disposable,
  and reconcilable — the same authority split `coordinator-task-status-renderer`
  already established for `tasks.md`.
- **Rehydratable role, not resident process.** Any fresh session that loads the
  supervisor handoff becomes the supervisor (Gas Town's Nondeterministic
  Idempotence). No always-on host is required for Phase 1; ri-08's daemon later
  *wakes* supervisor sessions rather than replacing them.
- **Escalate only real decisions.** Every human touchpoint routes through the
  trust posture + approval gate service. Auto where delegated, notify with
  timeout where reversible, block where it matters. No new gate prose.
- **One artifact per concept.** Loops close when every producer emits what the
  consumer reads. Candidate work gets one schema; review findings get one schema;
  neither lives inlined in a vendor config string.

## Phase 1 — Supervisor Role and Contract

### Capability: Supervisor Archetype and Crew Manifest

Add a `supervisor` archetype to `agent-coordinator/archetypes.yaml`:
`write_capable: false`, `model: frontier`, with a system prompt centered on
decomposition, delegation, gate adjudication, and an explicit prohibition on
implementing directly. The supervisor is the judgment locus with low token volume
per decision; the expensive volume stays in the standard-tier implementer lane.
Repurpose the vestigial `agent-coordinator/teams.yaml` as the crew manifest —
supervisor plus the archetype roster and which vendors may fill each role — or
delete it; it must stop being an unwired file that looks load-bearing.

Acceptance outcomes:
- `POST /archetypes/resolve_for_phase` can resolve the supervisor archetype; the
  resolver rejects any attempt to mark it write-capable.
- `teams.yaml` is either consumed by a documented reader or removed; no vestigial
  team model remains.

### Capability: Supervise Skill (Conversational Entry Point)

New `skills/supervise/` — the single skill the human converses with. Its verbs
are the existing skills: intake turns a request into an OpenSpec change or
proposal and slots it via `/plan-roadmap`; execution fills
`autopilot-roadmap/scripts/orchestrator.py`'s `dispatch_fn(item_id, phase,
context)` seam, dispatching each `/autopilot` run as a background sub-agent in
its own worktree so the supervisor's context holds outcomes, never transcripts;
multiple concurrent changes fan out through the same seam. Every gate the stack
raises is evaluated through `skills/shared/approval_gate.py` against the repo's
`TRUST_POSTURE.md`. Depends on ri-06 (encode gates in code) so gate call sites
exist to route.

Acceptance outcomes:
- A single conversation can take a natural-language request to a merged PR with
  the human touched only at gates whose posture is not `auto`.
- Two roadmap items with disjoint file scopes progress concurrently from one
  supervisor session, each in its own worktree.
- The supervisor session never edits implementation files itself (audit-verified).

### Capability: Supervisor Handoff and Rehydration

Extend the coordinator handoff document (`agent-coordinator/src/handoffs.py`,
`HandoffDocument`) with a supervisor-scoped record: active changes and their
phases, pending gates with deadlines, standing decisions, and back-edge digest
state. The SessionStart hook already loads handoffs; a fresh session that loads
the supervisor handoff resumes the role with no other context. Escalations that
today die in handoff prose (e.g. "Phase IMPLEMENT sub-agent failed after 2
attempts") instead file through the `escalate_resume` gate so they notify rather
than wait to be discovered (consumes ri-05/ri-06 machinery; adds the routing).

Acceptance outcomes:
- Killing the supervisor session mid-roadmap and starting a fresh one loses no
  state: the new session lists active changes, pending gates, and next actions
  from the handoff alone.
- A twice-failed phase dispatch produces a gate evaluation and (under
  `notify_with_timeout`) a notification, never only a handoff note.

## Phase 2 — State Contracts

### Capability: Work-Queue Truth/Projection Contract

Document and enforce the split: `loop-state.json` is the authoritative execution
state; the coordinator work queue is a distribution/claim mechanism whose entries
are always derivable from loop-state. Queue submissions are keyed idempotently by
`(change_id, phase, iteration)` in `input_data` with submit-if-absent semantics;
ordering is outbox-style (persist loop-state, then enqueue); on resume, queue
entries are re-derived or cancelled from loop-state, never the reverse. Autopilot
and the supervisor mirror phase state into the queue so `apps/kanban-viz` shows
live truth instead of an empty board. The queue's claim atomicity is exercised
only in the coordinated tier; local-parallel and sequential tiers remain
coordinator-free, preserving the three-tier availability design.

Acceptance outcomes:
- The contract is stated in `docs/guides/` and `skills/coordination-bridge/SKILL.md`;
  no skill reads authoritative phase state from the queue (grep-enforced in tests).
- Re-submitting the same `(change_id, phase, iteration)` is a no-op; crash between
  state-write and enqueue reconciles cleanly on resume.
- kanban-viz reflects a live autopilot run's phases within one poll interval.

### Capability: Durable State Artifacts Guide

One guide documenting every durable artifact — `loop-state.json` (per change),
roadmap `checkpoint.json`, `learnings/<item>.md`, phase records, handoff
documents — stating what each holds, who writes it, and the rehydration order a
fresh session follows. This is what makes the "throw sessions at the role"
property real rather than folklore spread across five skill docs.

Acceptance outcomes:
- A single `docs/guides/state-artifacts.md` exists and each skill doc links to it
  instead of restating semantics.
- The supervise skill's rehydration step follows the guide's documented order.

## Phase 3 — Back-Edge Standardization

### Capability: Canonical Candidate-Work Schema

Define one proposal-stub schema (JSON Schema under `openspec/schemas/`) that every
discovery generator emits — bug-scrub findings promoted to candidates,
improve-harness proposal stubs, explore-feature shortlist entries — carrying
provenance (source artifact, finding IDs), effort/priority estimates, and
suggested change-id. `/prioritize-proposals` consumes only this schema; the
supervisor's periodic digest to the human ranks these stubs and approved ones
enter `/plan-roadmap` as roadmap items. Upstream-compatible with the always-on
proposal's Findings-to-Issues Pipeline (Phase 6): the tracker adapter files
issues *from* the same stubs rather than defining a fourth shape.

Acceptance outcomes:
- All three generators emit schema-valid stubs; `/prioritize-proposals` rejects
  non-conforming input.
- An approved stub becomes a roadmap item without hand-editing intermediate
  artifacts.

### Capability: Shared Review-Findings Schema Extraction

Extract the review findings schema — today inlined as a JSON string in
`agent-coordinator/agents.yaml` (grok's `--json-schema` arg) while
`review_dispatcher.py` and `consensus_synthesizer.py` carry parallel
expectations — into one canonical schema file referenced by all three. Schema
drift between a vendor adapter and the consensus layer reproduces the
silent-false-consensus failure class already hit once (pi `--no-tools`).

Acceptance outcomes:
- One schema file; `agents.yaml` references it (adapter inlines at dispatch
  time); dispatcher and synthesizer validate against it.
- A deliberately drifted finding fails validation loudly instead of merging
  silently into consensus.

## Phase 4 — Hygiene

### Capability: Memory-Layer Decision

Only episodic memory is consumed today; `memory_working` and `memory_procedural`
are empty tables with documented ambitions. Either wire procedural memory as the
home for roadmap `learnings/<item>.md` content (queryable by the replanner and
the supervisor's digest) or descope the two layers from schema and docs. A
three-layer cognitive architecture with two empty layers is documentation debt
that misleads contributors and agents alike.

Acceptance outcomes:
- Procedural memory has a writer and a reader in the roadmap loop, **or** the
  unused layers are removed from schema, bridge surface, and docs — no third state.

## Dependencies and Sequencing

1. ri-06 (encode autopilot gates in code) — prerequisite for the supervise
   skill's gate routing; land first.
2. Phase 1 and Phase 2 of this proposal are independent of each other and can
   proceed in parallel; Phase 3 depends on neither but should precede the
   always-on Phase 6 tracker work it feeds.
3. The in-flight router changes (`implement-the-task-router-vendor-x-location-x-model`,
   `make-the-orchestrator-obey-the-router`) should land before the supervisor
   adds any vendor-preference policy (e.g. pi for API-metered lanes); the router
   is the single place that answers "which vendor/model/tier".
4. ri-08 (dispatcher daemon) composes later: the daemon wakes supervisor sessions
   on events; nothing in this proposal blocks on an always-on host.

## Out of Scope

- **The dispatcher daemon and always-on host** (ri-08/ri-09) — the supervisor is
  rehydratable without them.
- **pi harness consolidation for non-Claude vendors** — a router-policy decision
  gated on the in-flight router changes and a gen-eval cost-per-successful-task
  comparison; separate change.
- **Auto-merge posture changes** — the human merge gate default is untouched.
- **New notification channels, tracker adapters, or scheduled discovery** —
  owned by the always-on proposal's phases.
