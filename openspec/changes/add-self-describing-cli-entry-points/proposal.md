# Give cross-skill scripts self-describing CLI interfaces

> Parent roadmap: `skill-rightsizing`
> Change ID: `add-self-describing-cli-entry-points`
> Effort: L
> Priority: 1

## Summary

Add console entry points in skills/pyproject.toml for the shared scripts, so every cross-skill call becomes a named command that accepts --json, exits non-zero with an actionable message, and documents itself through --help.

## Dependencies

- `ri-09`

## Acceptance Outcomes

- No SKILL.md contains a <skill-base-dir> placeholder or a sys.path.insert line.
- Every shared command supports --json and --help.
- Failure paths exit non-zero with a message naming the corrective action.
- The "run it BARE — do not pipe" warning class is removed because exit status is no longer ambiguous.

## Rationale

104 hard-coded relative paths and 243 <skill-base-dir> placeholders make the skill tree a build system with no build tool. A self-describing interface means the skill prose no longer has to teach the model how to call it.
