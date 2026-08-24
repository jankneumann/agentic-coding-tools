# Rewrite skill frontmatter to what the runtime reads

> Parent roadmap: `skill-rightsizing`
> Change ID: `rewrite-skill-frontmatter`
> Effort: M
> Priority: 1

## Summary

Delete the dead triggers field from all 52 skills that carry it, audit category and tags for any real consumer, and rewrite all 74 descriptions to state both what the skill does and when to use it.

## Dependencies

- `ri-04`
- `ri-09`

## Acceptance Outcomes

- No SKILL.md contains a triggers field.
- All 74 descriptions state both capability and trigger condition in third person.
- The /doctor listing context cost is re-measured and compared against the ri-04 baseline.
- Skill-selection accuracy on a held-out set of natural user phrasings does not regress.

## Rationale

Nothing in the repository reads triggers, while 69 of 74 descriptions omit the when-to-use clause that actually drives skill selection. This is the cheapest change with a measurable payoff.
