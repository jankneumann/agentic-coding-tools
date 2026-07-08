# Schedule daily discovery refresh

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `schedule-daily-discovery-refresh`
> Effort: M
> Priority: 3

## Summary

Run refresh-architecture, tech-debt-analysis, and bug-scrub daily on the daemon schedule (staggered, posture-gated), keeping architecture artifacts under 24 h old and producing dated machine-readable findings.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- All three analyses run daily unattended with timestamped artifacts; the architecture graph is never older than 24 h.
- A failed refresh emits a notification rather than silently serving stale artifacts.
- fix-scrub auto-fix lane runs against fresh findings under the posture auto ceiling only.

## Rationale

validate-feature architecture checks and prioritization inputs drift when analysis artifacts go stale; discovery must be continuous for backlog automation to be trustworthy.
