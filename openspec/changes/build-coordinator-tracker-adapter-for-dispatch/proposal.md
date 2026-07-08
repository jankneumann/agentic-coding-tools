# Build coordinator tracker adapter for dispatch

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `build-coordinator-tracker-adapter-for-dispatch`
> Effort: M
> Priority: 2

## Summary

Implement the symphony coordinator-tracker-adapter item, a work-source adapter over the coordinator issue tracker's ready-issues query that yields dispatchable items with dependency-aware claiming and no duplicate handout.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- Adapter returns only ready (unblocked) issues and claims are exclusive under concurrent polls.
- Fifty or more issues can be enumerated and claimed with no duplicate dispatch in an integration test.

## Rationale

The daemon needs a clean work-source boundary over the existing tracker; splitting it from the daemon keeps each piece independently reviewable.
