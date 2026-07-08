# Add GitHub two-way tracker adapter

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `add-github-two-way-tracker-adapter`
> Effort: L
> Priority: 2

## Summary

Elevate the symphony github-tracker-adapter from one-way projection to bidirectional sync: GitHub Issues as human-facing system of record, coordinator issue tracker as the claim ledger, labels carrying ready/claimed/blocked/needs-human status.

## Dependencies

- `ri-07`
- `ri-08`

## Acceptance Outcomes

- An issue labeled ready on GitHub is dispatchable within one poll interval, with claim/progress/closure visible on GitHub.
- Concurrent dispatcher polls never claim the same GitHub issue twice.
- Human edits on GitHub (close, re-label, comment commands) reach the coordinator within one sync interval.

## Rationale

Aligns agent work tracking with human processes on GitHub while keeping exclusive claim semantics the platform lacks.
