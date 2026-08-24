# Change: Cross-harness session flow display

## Why

Zoetrope (github.com/furkankly/zoetrope) demonstrates that a Claude Code
session rendered as a live flow graph — agents as nodes, tool chips, a
scrubber timeline — is a materially better observability surface than raw
transcripts. But it is Claude-Code-only, local-filesystem-only, and
deliberately network-free, so it cannot cover our fleet of harnesses
(Claude Code CLI/web, Codex CLI/web, Antigravity, Grok, Pi) or sessions
running on ephemeral cloud containers.

This repository is the canonical home of every ingredient of a
generalized version, in disconnected pieces:

- `skills/collect-transcripts/` normalizes seven harnesses' transcripts
  into one `NormalizedEvent` schema with `tool_use_id` linkage and
  sequence ordering.
- `skills/langfuse/` ships a Stop hook that emits per-turn
  `as_type="agent"` observations with `as_type="tool"` children, grouped
  by `session_id` and tagged by harness — but it re-parses Claude Code
  JSONL with a private parser instead of reusing the adapters, and
  consumer repos ship it unregistered.
- `agent-coordinator/` already runs an HTTP + Postgres service that every
  harness session reports to, and `apps/kanban-viz` establishes the
  React + Vite + Tauri pattern for visualization apps over coordinator
  data.

Nothing connects them: no app consumes Langfuse or transcript data, and
the hook and adapter paths maintain two divergent schemas for the same
underlying reality. (An earlier draft of this change lived in
`agentic-content-analyzer`, which only mirrors these skills; it moved
here because the source of truth — adapters, hook, coordinator — is
this repository, and every consumer repo inherits the capability
through skill mirroring.)

## What Changes

1. **Unify the capture substrate.** The Langfuse hook parses transcripts
   through the `collect-transcripts` adapters; its private
   `group_into_turns()` parser is deleted. `NormalizedEvent` gains the
   minimal linkage fields a flow graph needs (`parent_session_id`,
   `spawned_by_tool_use_id`, `agent_label`), with a schema version bump
   and regenerated `references/event-schema.md`.
2. **Make hook-based Langfuse logging the live capture path.** Stop /
   SubagentStop registration via the existing idempotent installer,
   gated on `LANGFUSE_ENABLED`, plus a batch uploader in
   `collect-transcripts` so hook-less harnesses reach the same Langfuse
   project post-hoc with identical observation vocabulary and harness
   tags.
3. **Add a read-only flow API to `agent-coordinator`.** Lists sessions
   and serves ordered fact streams from two sources — captured
   transcript JSONL (full fidelity, replay/seek) and the Langfuse API
   (cross-machine, near-live) — normalized server-side to one contract
   shape so Langfuse credentials stay off clients. Fail-soft on either
   source, matching the `query_metrics.py` posture.
4. **Add `apps/flow-viz`.** A visualization app following the
   `kanban-viz` conventions (React + Vite + Vitest, optional Tauri
   shell) that renders the fact stream as a flow graph with a
   content-time scrubber. Graph state is a pure, idempotent, commutative
   fold over facts — zoetrope's core invariant — so live-follow and
   replay of the same session converge to identical state.
5. **Reconcile self-hosted Langfuse host defaults** across the hook,
   consumer profiles, and docs (`:3050` vs `:3100` drift).

Out of scope: a Jules transcript adapter, changes to consumer-repo
application telemetry (e.g. `agentic-content-analyzer`'s
`ObservabilityProvider` Protocol), new coordinator mutation surfaces
(the flow API is read-only), and embedding the display in any consumer
repo's own frontend (consumers may later proxy the coordinator API).

## Capability

- `agentic-flow-display`

## Impact

New read-only coordinator routes, new `apps/flow-viz`, `collect-
transcripts` schema version bump with regenerated docs, the `langfuse`
skill hook loses its private parser, and consumer repos pick up the
unified hook through normal skill mirroring plus their own opt-in hook
registration. Coordinator write paths, work-queue truth contracts, and
consumer application code are untouched.
