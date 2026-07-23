# Complete incremental semantic indexing

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `complete-incremental-semantic-indexing`
> Effort: L
> Priority: 2

## Summary

Finish index_repo so it executes the CocoIndex and Postgres pipeline as a durable, idempotent operation for an exact repository revision. Apply changed-file processing, permitted-scope filtering, and an explicit not-configured state when no embedder is available.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- index_repo completes against a reachable Postgres and embedder environment without raising NotImplementedError.
- Reindexing a revision processes only changed eligible files and reuses the durable operation for duplicate repository-and-commit requests.
- Ignored files, secrets, generated dependency trees, and files outside the permitted read scope are excluded from indexing.
- Missing Postgres or embedding configuration produces an explicit not-configured or failed record and preserves exact-search fallback behavior.
- Embedding configuration explicitly integrates with add-coordinator-llm-gateway when available without making embeddings a production-default requirement.

## Rationale

The existing semantic-search surfaces cannot support the refresh lifecycle until indexing actually runs, records durable outcomes, and remains safe when Postgres or embeddings are unavailable.
