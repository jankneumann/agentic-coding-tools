# Invert the skill test suite from shape assertions to behavioural scenarios

> Parent roadmap: `skill-rightsizing`
> Change ID: `invert-skill-test-suite-to-behavioural`
> Effort: M
> Priority: 2

## Summary

Retire the content-invariant tests that assert structure — tail-block presence, minimum row counts, section ordering — and replace them with three behavioural scenarios per user-invocable skill drawn from the replay harness.

## Dependencies

- `ri-17`

## Acceptance Outcomes

- Frontmatter parsing and reference resolution checks are retained; shape assertions are removed.
- Each user-invocable skill has at least three behavioural scenarios wired into CI.
- Total skill test line count falls while measured behavioural coverage rises.
- A deliberately broken skill fails its behavioural scenarios.

## Rationale

24,740 lines of test code currently police 17,945 lines of prose without ever executing a skill, so a skill can be structurally perfect and behaviourally broken. This is the mechanism that makes every change expensive.
