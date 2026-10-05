# Add human principals and the git-native ownership map

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `ownership-map`
> Effort: L
> Priority: 1

## Summary

Extend the principal-credential-architecture registry with human principals (domains, availability), add a schema-validated openspec/owners.yaml assigning owners, decision rights, and acceptance rights to capabilities, roadmap items, and contract paths, and ship a resolver library plus CODEOWNERS emit/reconcile.

## Dependencies

- None

## Acceptance Outcomes

- A schema-validated openspec/owners.yaml resolves an owner set for any capability, roadmap item, or contract path, falling back to a declared repository-default owner.
- A check reports capabilities with no owner and owners that are not registered principals in the extended principal registry (no separate registry is created).
- With no owners.yaml present, every resolver call returns the sole repository principal and the existing skill test suites pass unchanged (solo mode).
- The resolver works from the git checkout alone with the coordinator unavailable, and CODEOWNERS generated from owners.yaml produces no routing disagreements in a reconcile check.
- owners.yaml is registered in docs/guides/state-artifacts.md with writer, authority, and missing/stale behavior.

## Rationale

Explicit principals (P1) and owned decisions (P2, P3) are the substrate for routing, attribution, intent ownership, and owner acceptance; every team-mode behavior asks 'who owns X?'. Extending the existing registry avoids the parallel-registry the constraints forbid.
