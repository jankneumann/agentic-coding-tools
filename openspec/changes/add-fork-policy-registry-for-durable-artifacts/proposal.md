# Add fork policy registry for durable artifacts

> Parent roadmap: `durable-execution`
> Change ID: `add-fork-policy-registry-for-durable-artifacts`
> Effort: M
> Priority: 2

## Summary

Introduce a machine-readable registry next to the state-artifacts.md inventory declaring a fork policy (fork_point, latest, or fresh) for every durable artifact class, including the effects journal and phase-progress journal, and have each owning writer enforce its policy at read time.

## Dependencies

- None

## Acceptance Outcomes

- Every artifact class listed in docs/guides/state-artifacts.md, plus effects.jsonl and phase-progress journals, has exactly one fork policy entry in the registry, enforced by a test that diffs the inventory against the registry.
- Owning readers of latest-policy artifacts (checkpoint.json, supervisor cycle ledger, generated docs/decisions/) resolve the main-line value rather than a forked copy, covered by a unit test per policy.
- The registry is deterministic and does not change the supervisor cycle fingerprint.

## Rationale

Phase 1 safety foundation; fork semantics are convention today and violations surface only as merge conflicts or stale reads, so policies must be explicit before enforcement checks and sync-point skills can reference them.
