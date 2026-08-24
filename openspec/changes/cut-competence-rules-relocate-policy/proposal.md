# Cut competence-restating rules and relocate genuine project policy

> Parent roadmap: `skill-rightsizing`
> Change ID: `cut-competence-rules-relocate-policy`
> Effort: M
> Priority: 2

## Summary

Apply the keep/cut test — does this encode a project-specific decision, or describe ordinary competence — across all skill prose, deleting the second category and moving surviving policy such as feature-flag, safe-default and rollback requirements into CLAUDE.md where it is stated once.

## Dependencies

- `ri-09`

## Acceptance Outcomes

- Every surviving imperative in a SKILL.md traces to a project-specific decision, recorded in the change's spec delta.
- Feature-flag, safe-default and rollback policy appears exactly once, in CLAUDE.md.
- Total MUST/CRITICAL/NEVER occurrences across skills falls, and every remainder is justified in review.
- Replay results are non-inferior to the ri-09 baseline.

## Rationale

Rules that restate how a competent engineer already works compete with the model's own judgment and dilute the rules that carry real information.
