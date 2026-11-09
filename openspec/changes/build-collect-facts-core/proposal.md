# Build collect-facts core with provenance, redaction, and audit

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `build-collect-facts-core`
> Effort: L
> Priority: 2

## Summary

Add a collect-facts <trace-id | change-id | PR> command that writes facts with full provenance into an evidence ledger from the coordinator audit trail, causal-trace-linked events, git range and diff stats, and the effects journal when present. Access is read-only, scoped to one investigation, time-limited, audited, and secret-redacted before facts are written.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- Given a causal trace ID, collect-facts produces a schema-valid ledger whose facts each carry source, gathered_by, time_window, and tool_version.
- A missing source (e.g. no effects journal yet) produces an explicit source_unavailable fact rather than a failure.
- A secret-pattern fixture placed in a source is redacted in the output, and every invocation writes an audit record.
- Collection performs no mutations of source systems; its only writes are the target ledger and its audit record, and it refuses to run past its configured time limit.

## Rationale

Default-on fact collection removes the piecemeal gathering that made agents skip the factual tier. The read-only, scoped, audited, redacted constraints must be built into the core so every later source adapter inherits them.
