# Make architecture refresh revision-aware

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `make-architecture-refresh-revision-aware`
> Effort: M
> Priority: 4

## Summary

Replace mtime-based architecture freshness and subprocess-local operation state with deterministic input tracking tied to a Git revision and durable cross-process status. Preserve refresh-architecture as the canonical architecture producer.

## Dependencies

- None

## Acceptance Outcomes

- Architecture artifacts record their source Git SHA, producer version, and relevant input fingerprint.
- Architecture check mode reports stale output from changed inputs regardless of file modification time.
- Refresh operation state survives process exit and can be queried from a separate process.
- Two refreshes for the same revision and inputs produce identical repository artifacts and no second diff.

## Rationale

Architecture artifacts cannot participate in reliable convergence while a six-hour mtime window or process-local singleton can report stale output as fresh.
