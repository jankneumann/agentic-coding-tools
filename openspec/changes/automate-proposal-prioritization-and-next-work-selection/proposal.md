# Automate proposal prioritization and next-work selection

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `automate-proposal-prioritization-and-next-work-selection`
> Effort: L
> Priority: 2

## Summary

Extend prioritize-proposals into a scheduled decision layer: daily scoring of proposals, roadmap items, and open issues on dependency-readiness, value, effort, staleness, and live episodic-memory signals; top-N ready items auto-enqueue to the dispatcher under a notify-with-veto posture; explore-feature proposes candidates when the ready queue runs dry.

## Dependencies

- `ri-05`
- `ri-08`
- `ri-22`

## Acceptance Outcomes

- A daily prioritization report ranks all active proposals and ready roadmap items with per-factor scores, delivered via the notification service.
- Under the default posture, top-N picks auto-enqueue after the veto window; a veto prevents enqueue; under block, nothing enqueues without approval.
- The dispatcher queue is never empty while unblocked candidate work exists over a 7-day soak.
- When no ready work exists, an explore-feature run proposes candidates as draft issues.

## Rationale

Automating build/validate/merge without automating what-next leaves the daemon starved or human-bottlenecked; selection is the remaining manual step in the loop.
