# Inject scoped semantic context into coding jobs

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `inject-scoped-semantic-context-into-coding-jobs`
> Effort: L
> Priority: 12

## Summary

Extend context-engineering and coding workflows to request bounded, deduplicated semantic results for the exact task revision and permitted scope. Supply explicit provenance and fall back to rg and direct source reading whenever semantic search is stale, unavailable, mismatched, or out of scope.

## Dependencies

- `ri-03`
- `ri-08`

## Acceptance Outcomes

- context-engineering requests CAN_CODE_SEARCH results for the exact repository revision and work-package read scope.
- implement-feature, quick-task, iterate-on-implementation, debugging, validation, and implementation review can receive a bounded Semantic code context section.
- Every injected hit includes file, line range, score, indexed commit, and scope decision.
- Duplicate or over-budget hits are omitted deterministically.
- Tests prove stale, unavailable, mismatched, and out-of-scope results trigger explicit exact-search fallback without blocking the coding job.

## Rationale

Current semantic context becomes useful only when implementation, debugging, review, and validation jobs can consume it without weakening revision or scope safety.
