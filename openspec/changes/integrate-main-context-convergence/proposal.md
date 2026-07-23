# Integrate main context convergence

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `integrate-main-context-convergence`
> Effort: L
> Priority: 11

## Summary

Make merge-pull-requests run exactly one shared context convergence after each successful merge, invoking cleanup-feature --post-merge first for OpenSpec changes. Commit and push deterministic output as one follow-up convergence commit, then enqueue semantic indexing for the final pushed main SHA.

## Dependencies

- `ri-07`
- `ri-10`

## Acceptance Outcomes

- OpenSpec merge paths invoke cleanup-feature --post-merge for task migration, archive, and spec-delta merge before running the shared refresh.
- Non-OpenSpec and OpenSpec merge paths each run exactly one convergence operation for the resulting main state.
- Deterministic cleanup and refresh artifacts plus the manifest are committed and pushed as one follow-up convergence commit.
- Sync-point locking and durable operation identities prevent interleaved main writers, duplicate commits, duplicate indexing, and double archival during retries.
- The final handoff reports the merged SHA, context-refresh SHA, and semantic-index status for the final pushed main SHA.

## Rationale

merge-pull-requests is the authoritative main synchronization point, while cleanup-feature must retain sole ownership of OpenSpec migration, archive, and spec-delta merge.
