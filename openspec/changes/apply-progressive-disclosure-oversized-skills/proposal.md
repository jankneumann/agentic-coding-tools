# Apply progressive disclosure to the eleven oversized skills

> Parent roadmap: `skill-rightsizing`
> Change ID: `apply-progressive-disclosure-oversized-skills`
> Effort: L
> Priority: 2

## Summary

Restructure each SKILL.md over 500 lines into an index plus reference files one level deep, so a run loads only the phases it actually needs.

## Dependencies

- `ri-12`
- `ri-13`
- `ri-14`

## Acceptance Outcomes

- No SKILL.md exceeds 500 lines.
- All reference files link directly from their SKILL.md with no nested references.
- Reference files over 100 lines carry a table of contents.
- Measured per-run context consumption falls for at least one skill where a phase is skipped.

## Rationale

66 of 74 skills have no progressive disclosure at all; the 887-line validate-feature loads in full whether or not the run includes the E2E phase. Sequenced after the deletion items because they touch the same files.
