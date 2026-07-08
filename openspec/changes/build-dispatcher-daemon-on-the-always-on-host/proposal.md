# Build dispatcher daemon on the always-on host

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `build-dispatcher-daemon-on-the-always-on-host`
> Effort: L
> Priority: 2

## Summary

A long-running systemd service on the GX10 polling the tracker adapter on a fixed cadence, spawning headless vendor-CLI sessions running /autopilot or /autopilot-roadmap under a global concurrency cap, each with a distinct AGENT_ID, recovering after restart purely from tracker, worktree, and loop-state.json state.

## Dependencies

- `ri-06`
- `ri-07`

## Acceptance Outcomes

- 24 hours unattended with no leaked workspaces and at least 50 issues processed with no duplicate dispatch.
- kill -9 of the daemon followed by restart resumes every in-flight item from its checkpoint without re-dispatch.
- Spawned sessions have unique agent identities visible in discover_agents, and handoff reads use explicit agent names.

## Rationale

Nothing in the repo starts sessions today; this is the symphony dispatcher-daemon item and the core of the non-interactive software-factory runner.
