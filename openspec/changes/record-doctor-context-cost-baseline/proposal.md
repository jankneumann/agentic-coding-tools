# Record the /doctor context-cost baseline

> Parent roadmap: `skill-rightsizing`
> Change ID: `record-doctor-context-cost-baseline`
> Effort: S
> Priority: 2

## Summary

Run the /doctor setup checkup against the repository and commit its findings as a dated baseline — the always-loaded skill-listing context cost, its biggest contributors, the unused-skill list, and any slow SessionStart hooks.

## Dependencies

- None

## Acceptance Outcomes

- A committed dated report states the total skill-listing context cost and names its top contributors.
- Skills never triggered in the available transcript history are listed as deletion candidates.
- Any SessionStart hook flagged as slow is recorded with its measured duration.

## Rationale

Every skill's name and description is preloaded into every session, so the listing is a fixed per-turn tax. Establishing the number before any edits gives the frontmatter work a denominator.
