# Add the /reconcile skill for divergent branches and specs

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `reconcile-skill`
> Effort: L
> Priority: 3

## Summary

Add a /reconcile skill that runs /audit-choices per branch, extracts contracts and concerns-as-tests, builds an agree / complementary / conflicting / unique matrix, routes each conflict to its owner as a typed decision, and emits an OpenSpec change for the reconciled contract plus the test union, reusing synthesize_variants().

## Dependencies

- `ri-09`
- `ri-14`
- `ri-15`

## Acceptance Outcomes

- Given two branches, /reconcile produces a reconciliation matrix in which every conflicting item names an owner and a pending decision.
- The output change validates with openspec validate --strict and includes the reconciled test union as acceptance tests.
- Given two competing proposals for one capability, the workflow emits a kernel/backlog split with no requirement from either proposal silently dropped.
- /reconcile runs with only the git remote available, and conflicts between principals' intents are escalated rather than resolved by the agent.

## Rationale

P6 reconciles insight rather than diffs; this is the direct fix for the competing-spec half of the motivating incident and lifts the existing /prototype-feature synthesis path to many principals.
