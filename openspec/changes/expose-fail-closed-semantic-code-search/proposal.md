# Expose fail-closed semantic code search

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `expose-fail-closed-semantic-code-search`
> Effort: M
> Priority: 3

## Summary

Wire the semantic query service into coordinator startup and capability discovery with exact revision matching and provenance-rich responses. Return an explicit stale or unavailable state instead of serving mismatched results.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- Coordinator startup initializes the query service from durable registry state and supports successful queries against a usable index.
- Capability discovery reports CAN_CODE_SEARCH only when the query service is initialized and a usable index exists.
- Every query response identifies the indexed repository and commit.
- A requested revision mismatch returns no results as current and supplies an explicit exact-search fallback state.
- Query scope filters enforce the caller's read_allow and deny boundaries.

## Rationale

Agents must be able to discover usable code search while never silently consuming an index for a different revision.
