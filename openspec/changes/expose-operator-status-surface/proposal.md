# Expose operator status surface

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `expose-operator-status-surface`
> Effort: M
> Priority: 4

## Summary

Implement symphony's operator-http-status-surface (/api/v1/state, /healthz, /metrics sidecar) or extend kanban-viz with a live view of daemon queue depth, in-flight sessions and phases, gate decisions awaiting approval, next sync window, and vendor budget state.

## Dependencies

- `ri-05`
- `ri-08`

## Acceptance Outcomes

- One URL answers what the daemon is doing right now and what it is waiting on.
- Pending gate decisions and the next sync window are visible on the surface.

## Rationale

An always-on system needs one place answering "what is the daemon doing and what is it waiting on"; the /sync-points/status local-disk registry coupling is satisfied by the single-box GX10 layout but must be fixed before splitting hosts.
