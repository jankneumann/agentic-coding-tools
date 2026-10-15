# Add rule-to-enforcer registry with expiring waivers

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `add-rule-to-enforcer-registry-with-expiring-waivers`
> Effort: L
> Priority: 2

## Summary

Create docs/enforcement/rules.yaml with one row per project rule (id, statement, enforcement level, enforcer path, proven-failing commit, source), generate a drift-checked rule-to-enforcer table in AGENTS.md from it, add line-level waivers with rule id, reason, expiry and approver, and add a prove_enforcer helper. Seed it with the existing guards and the Phase 1 fail-closed guards.

## Dependencies

- `ri-01`
- `ri-02`
- `ri-04`

## Acceptance Outcomes

- A guard test fails when any registry row with a level other than docs names an enforcer path that does not exist or lacks a recorded failing commit, and it ships with a self-test proving it detects that violation.
- prove_enforcer <rule-id> demonstrates failure on the recorded commit for every seeded rule, including the openspec-path-stability, CI-coverage and skill-loader-frontmatter guards.
- The AGENTS.md rule-to-enforcer table is generated from the registry, and a drift check fails when they diverge.
- A waiver with a past expiry date, or one missing a reason or approver, fails the waiver guard.
- The registry documents the escalation rule (a docs-level rule corrected twice is flagged for promotion) as an interface for intervention records, and adds no correction store or mining logic.

## Rationale

Rules live in prose with no index to what enforces them and no waiver-with-expiry mechanism; the registry is the shared infrastructure Phase 2 principles and the plan linter build on, and it exposes rule ids for intervention-capture to link to without creating a second correction store.
