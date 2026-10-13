# Extend collect-facts with config, model, memory, and snapshot sources

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `extend-collect-facts-sources`
> Effort: M
> Priority: 5

## Summary

Add collect-facts source adapters for resolved config and feature-flag values, the vendor/model/tier used, relevant episodic memories from the closed-loop-learning store, and the latest signal snapshots. Each adapter inherits the core's provenance, redaction, audit, and source_unavailable behaviour.

## Dependencies

- `ri-05`
- `ri-07`

## Acceptance Outcomes

- For a fixture change-id, the ledger contains facts for resolved feature-flag values, the vendor/model/tier used, and the latest signal snapshot, each with full provenance.
- Episodic memories are read from the existing closed-loop-learning store, with no new store created.
- Disabling any one adapter yields a source_unavailable fact for it while the other sources still populate.

## Rationale

The proposal lists these sources as part of the default factual tier. They depend on the snapshot format and are separable from the core so the core can ship in Phase 2.
