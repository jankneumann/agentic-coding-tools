# Harden heartbeats and worktree registry for daemon operation

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `harden-heartbeats-and-worktree-registry-for-daemon-operation`
> Effort: L
> Priority: 2

## Summary

Wall-clock heartbeating of every active session's worktree by the daemon, scheduled worktree.py gc, flock-based locking or per-entry files for the registry, and documented reconciliation of the four staleness clocks (15 min, 1 h, 2 h, 24 h) against daemon cadences.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- A 3-hour non-interactive phase is never flagged stale by the watchdog or the sync-point guard.
- 20 concurrent setup/heartbeat/teardown operations lose zero registry updates.
- Stale worktree count on the daemon host is bounded over a 7-day soak.
- The four staleness clocks are documented with their reconciled values.

## Rationale

Worktree and session infrastructure assumes interactive turns (Stop-hook heartbeats, last-writer-wins registry, unscheduled GC), which makes long headless phases look dead and loses concurrent updates.
