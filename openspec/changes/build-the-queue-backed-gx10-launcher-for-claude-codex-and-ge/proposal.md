# Build the queue-backed GX10 launcher for Claude, Codex, and Gemini workers

> Parent roadmap: `operator-front-door`
> Change ID: `build-the-queue-backed-gx10-launcher-for-claude-codex-and-ge`
> Effort: L
> Priority: 2

## Summary

Grow the pilot launcher into a service that claims signed dispatches from the coordinator queue, asks the governor for placement, and starts claude remote-control, codex exec, or Gemini workers by archetype in managed worktrees under herdr, with restart re-adoption and GX10 local models writing card prose and digests. It also owns the scheduled supervisor discovery cycle, enqueuing a weekday supervisor dispatch from the GX10 rather than the cloud harness.

## Dependencies

- `ri-05`
- `ri-06`
- `ri-08`

## Acceptance Outcomes

- Claiming a Claude-archetype dispatch from the queue starts a claude remote-control session in a fresh managed worktree that appears in the Claude app session list and records sub-agent phase dispatch rather than phase_fallback_inline.
- Claiming a dispatch whose archetype names Codex as primary implementer starts a codex exec worker in a managed worktree that returns a schema-valid dispatch result.
- A dispatch with an invalid signature or for a repository not on the allowlist is refused and logged with no process started, and no worker receives a permission mode beyond its archetype's declared mode.
- After a launcher restart, in-flight workers are re-adopted or their dispatches requeued using only coordinator, worktree, and loop-state records.
- Decision cards and digests produced for launcher-run dispatches are written by a GX10 local model, and the usage ledger shows zero subscription tokens spent on them.
- 24 hours unattended processes at least 50 queued dispatches with no duplicate dispatch and no leaked worktrees, and a kill -9 of the launcher followed by restart resumes every in-flight dispatch from its checkpoint without re-dispatch.
- Every launched worker has a unique agent identity visible in discover_agents, and handoff reads use explicit agent names.
- A scheduled supervisor discovery cycle fires from the GX10 on the configured weekday cadence as a queued dispatch, delivers a ranked digest to the Supervisor thread, and stops at the approval gate without creating roadmaps, dispatching implementers, or pushing.

## Rationale

Makes Remote Control and vendor workers the default execution path, so autopilot workers are always top-level sessions with archetype routing and Codex can act as primary implementer. Operator decision 2026-10-14 (3a): supersedes always-on-agent-automation ri-08 (dispatcher daemon) and inherits its unattended-soak, agent-identity, and scheduled-supervisor-cycle outcomes. always-on-agent-automation ri-09 (heartbeat and worktree-registry hardening) follows this item rather than preceding it, since it hardens the running launcher.
