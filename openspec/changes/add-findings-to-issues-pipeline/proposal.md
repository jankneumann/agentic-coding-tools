# Add findings-to-issues pipeline

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `add-findings-to-issues-pipeline`
> Effort: M
> Priority: 3

## Summary

Normalize bug-scrub, tech-debt, architecture, and capability-gap findings into deduplicated GitHub issues with provenance links and severity/type labels; route auto-fixable findings to a fix-scrub dispatch lane.

## Dependencies

- `ri-21`
- `ri-22`

## Acceptance Outcomes

- A bug-scrub finding becomes exactly one GitHub issue (re-runs update, never duplicate) with a provenance link.
- Labels distinguish auto-fixable from needs-planning findings; the former are dispatchable to fix-scrub.
- Closing the issue on GitHub retires the finding from subsequent scrub reports.

## Rationale

Gives humans and agents one shared backlog: humans see findings on GitHub, agents consume the same issues through the dispatcher.
