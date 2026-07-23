# Add durable context refresh records

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-durable-context-refresh-records`
> Effort: M
> Priority: 6

## Summary

Define and persist the refresh-operation identity, producer result model, and machine-readable manifest used by all refresh callers. Represent deterministic Git artifacts separately from the durable semantic-index operation and registry record.

## Dependencies

- None

## Acceptance Outcomes

- A refresh operation is durably identified by repository and source revision and can be queried after the triggering process exits.
- The manifest records source revision, producer versions, changed artifacts, validation results, semantic-index operation status, and degraded fallbacks.
- Every producer result uses one of fresh, degraded, failed, or not-configured and includes actionable remediation.
- The schema distinguishes staged repository artifacts from external semantic-index state.
- Recreating a record for the same repository and source revision reuses the existing operation identity.

## Rationale

A shared contract is needed for idempotent retries, cross-process status queries, actionable degradation reporting, and convergence handoffs.
