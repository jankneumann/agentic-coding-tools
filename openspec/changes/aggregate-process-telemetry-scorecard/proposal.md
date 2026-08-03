# Aggregate process telemetry into a comparable scorecard feed

> Parent roadmap: `skill-rightsizing`
> Change ID: `aggregate-process-telemetry-scorecard`
> Effort: M
> Priority: 2

## Summary

Extract turns, tool calls, tokens, retries, ESCALATE transitions, rework-report entries and time-to-green from the existing langfuse, collect-transcripts, session-log and loop-state.json sources into a single per-run record suitable for arm comparison.

## Dependencies

- None

## Acceptance Outcomes

- A single command emits one JSON record per agent run with all named metrics populated.
- Records from at least two different vendor harnesses normalize to the same schema.
- The feed backfills from existing stored transcripts, not only from new runs.

## Rationale

These are observations rather than judgments, so nothing can grade itself. For the rightsizing question specifically they are the primary metric, and the instrumentation already exists but is not aggregated for this purpose.
