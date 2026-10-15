# Add deterministic plan-artifact linter

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `add-deterministic-plan-artifact-linter`
> Effort: M
> Priority: 2

## Summary

Add a script that structurally checks proposal.md (Why / What Changes / Impact plus extensible mandatory sections) and tasks.md (Spec scenarios, Files and Dependencies fields per task; resolvable scenario and dependency references; a verification task per requirement). Run it from plan-feature, iterate-on-plan and CI, and register it in the enforcement registry.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- On fixture plans the linter reports a missing Spec scenarios field and an unresolvable scenario reference, and it passes on the template-shaped fixture.
- CI blocks a newly created change that fails the linter and only warns for changes that existed before the linter landed.
- plan-feature and iterate-on-plan invoke the linter and surface its findings; their SKILL.md edits are line-neutral or go into references/, and Gate 1/Gate 2 are unchanged.
- The linter has a rules.yaml row with a recorded failing commit that prove_enforcer verifies, and its tests use change_dir() and pin no openspec/changes/<change-id>/ literals.

## Rationale

Plan artifacts today are checked only by an LLM following prose instructions; a deterministic linter is the host for add-verification-signals-contract-to-plan-feature's check and becomes a registry-backed enforcer once ri-05 lands.
