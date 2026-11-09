# Capture per-commit signal snapshots in validate-feature and gen-eval

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `capture-per-commit-signal-snapshots`
> Effort: M
> Priority: 4

## Summary

Define a signal snapshot format and have validate-feature and gen-eval record a snapshot per run, covering the signals declared in the change's verification-signals plus a default coordinator-instrumentation set (call counts, latency distributions, external calls). Snapshots are stored keyed by commit SHA in existing stores rather than a new parallel store.

## Dependencies

- `ri-06`

## Acceptance Outcomes

- validate-feature writes a snapshot JSON keyed by commit SHA that includes every signal declared in the change's verification-signals section.
- gen-eval runs record snapshots in the same format, validated by a shared snapshot schema.
- The snapshot includes the default coordinator signal set even when a change declares no signals of its own.

## Rationale

The baseline-diff gate, signal-asserting regression scenarios, and collect-facts all need a stable snapshot format and per-commit history before they can compare signals instead of test outcomes.
