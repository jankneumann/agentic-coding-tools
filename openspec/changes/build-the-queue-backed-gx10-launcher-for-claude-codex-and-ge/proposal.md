# Build the queue-backed GX10 launcher for Claude, Codex, and Gemini workers

> Parent roadmap: `operator-front-door`
> Change ID: `build-the-queue-backed-gx10-launcher-for-claude-codex-and-ge`
> Effort: L
> Priority: 2

## Summary

Grow the pilot launcher into a service that claims signed dispatches from the coordinator queue, asks the governor for placement, and starts claude remote-control, codex exec, or Gemini workers by archetype in managed worktrees under herdr, with restart re-adoption and GX10 local models writing card prose and digests.

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

## Rationale

Makes Remote Control and vendor workers the default execution path, so autopilot workers are always top-level sessions with archetype routing and Codex can act as primary implementer. Supersedes always-on-agent-automation ri-08 where they conflict; the ri-09 heartbeat and worktree-registry hardening remains an external prerequisite.
