# Collect the 25 test directories CI never runs

> Parent roadmap: `skill-rightsizing`
> Change ID: `collect-uncollected-skill-tests`
> Effort: M
> Priority: 1

## Summary

Resolve the bare-module-name collisions that make roughly half the skill test directories uncollectable in the default sweep, then add them to pytest testpaths so they run in CI.

## Dependencies

- None

## Acceptance Outcomes

- Every directory under skills/tests/ containing test files is listed in testpaths.
- The default sweep collects all of them without import errors.
- Modules sharing a name across skills are namespaced or imported unambiguously.
- The number of tests collected by the default sweep is recorded before and after.

## Rationale

25 of the 52 directories under skills/tests/ are absent from the testpaths allowlist, including tests/plan-roadmap — which is how the scaffolder shipped invalid changes while its tests passed locally. They cannot simply be added; several skills expose a bare `models` module, so in a full sweep `models` resolves to whichever skill's scripts/ reached sys.path first. A comment in pyproject.toml already records this failure mode for one directory — a test CI never runs fails the same way as one that always passes.
