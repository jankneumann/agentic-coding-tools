# Implement project context refresh orchestration

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `implement-project-context-refresh-orchestration`
> Effort: L
> Priority: 7

## Summary

Add the shared refresh-project-context command or service that invokes canonical capability, API, architecture, decision, documentation, OpenSpec, and semantic-index producers. Stage deterministic outputs together and emit the durable manifest without collapsing producer ownership.

## Dependencies

- `ri-02`
- `ri-04`
- `ri-05`
- `ri-06`

## Acceptance Outcomes

- One command runs all configured context producers for a specified repository revision and emits a valid refresh manifest.
- A second run for the same revision produces no repository diff and reuses or verifies the same semantic-index operation.
- Failure or degradation of semantic indexing does not corrupt or discard successful deterministic producer output.
- Each producer remains independently runnable and its refresh result identifies its canonical owner.
- No refresh path independently writes main outside an authorized sync-point operation.

## Rationale

One idempotent operation must coordinate all project context so merge and branch workflows can reuse a single lifecycle.
