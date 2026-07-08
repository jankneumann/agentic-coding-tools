# Auto-seed scenarios from incidents

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `auto-seed-scenarios-from-incidents`
> Effort: M
> Priority: 4

## Summary

Auto-rollbacks, ESCALATE exits, and confirmed holdout failures generate bootstrap_from_incident scenario seeds with holdout visibility instead of relying on manual seeding.

## Dependencies

- `ri-15`

## Acceptance Outcomes

- Every auto-rollback event yields a draft holdout scenario linked to the incident.
- ESCALATE exits and confirmed holdout failures also produce draft scenario seeds.

## Rationale

Closes the regression loop automatically — today an un-reported escaped defect has no holdout scenario and can regress silently.
