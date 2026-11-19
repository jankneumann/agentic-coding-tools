# Add project-keyed gate projection

> Parent roadmap: `sandboxed-flow`
> Change ID: `add-project-keyed-gate-projection`
> Effort: L
> Priority: 2

## Summary

Project every pending gate from each enrolled repository (checkpoint.json, loop-state.json, TRUST_POSTURE.md and the approval service) into the coordinator, keyed by project, and expose one listing of everything awaiting the operator. The projection is rebuilt from the repositories and never written back; decisions go through the existing approval gate service.

## Dependencies

- None

## Acceptance Outcomes

- One coordinator request returns every pending gate across at least two enrolled repositories, each with project, gate type, subject, options and deadline.
- Deleting the projection and rebuilding it from the repositories yields the same pending set.
- A decision made through the listing reaches the owning repository's gate record through the existing approval service, with no new decision store.
- A repository the coordinator cannot reach is reported as degraded, not silently omitted.

## Rationale

Gate state is scattered across per-repository files with no cross-repository view; one inbox needs one listing while Git remains the authoritative record per repository.
