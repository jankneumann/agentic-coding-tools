# Add revision-aware semantic index registry

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-revision-aware-semantic-index-registry`
> Effort: M
> Priority: 1

## Summary

Introduce durable index identities, namespaces, freshness metadata, and lifecycle records keyed by repository and revision. Protect the canonical main index from feature and work-package namespaces and define explicit garbage collection.

## Dependencies

- None

## Acceptance Outcomes

- The registry records the exact indexed commit, model, embedding dimension, chunk count, completion status, and last error.
- Canonical main, feature-ref, and work-package indexes use distinct identities that cannot overwrite or masquerade as one another.
- Concurrent registry updates preserve one authoritative record per repository and revision.
- A documented garbage-collection operation removes eligible noncanonical namespaces without deleting the canonical main index.

## Rationale

Truthful semantic retrieval requires durable provenance and isolation before indexing or query surfaces can claim that results match a requested revision.
