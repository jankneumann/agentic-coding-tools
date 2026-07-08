# Implement quiet-window drain protocol in the dispatcher

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `implement-quiet-window-drain-protocol-in-the-dispatcher`
> Effort: M
> Priority: 2

## Summary

The dispatcher coordinates each sync window — stop dispatching, drain active sessions with a bounded wait (pinning long-runners for the next window), run /expedite then headless merge then cascading rebase of surviving branches, then resume dispatch.

## Dependencies

- `ri-08`
- `ri-09`
- `ri-12`

## Acceptance Outcomes

- Daily (configurable up to hourly) windows execute on the GX10 for a week with no guard --force overrides and no orphaned rebases.
- Dispatch throughput before and after windows shows drain-and-resume works with no starved queue.

## Rationale

Resolves the deadlock where a daemon keeping sessions perpetually alive would permanently block the repo-global active-agent guard, enabling daily-or-more-frequent merge sync points.
