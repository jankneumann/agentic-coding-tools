# Contracts: Merge Queue Scaling

## Evaluated Contract Sub-Types

### OpenAPI Contracts
**Not applicable.** This feature extends internal skill scripts and coordinator services. No new public API endpoints are introduced beyond the `/merge-train/metrics` GET endpoint, which is a read-only aggregation of existing audit data — its contract is defined by the metrics event schema in `design.md` D6.

### Database Contracts
**Not applicable.** No new database tables. Merge train state is stored in the existing `feature_registry.metadata` JSONB field (per the archived speculative-merge-trains proposal D1). Metrics are stored in the existing audit_log table.

### Event Contracts
**Applicable — defined inline in design.md D6.** The merge event schema is:
```json
{
  "timestamp": "ISO 8601",
  "event_type": "merge|revert|rebase|eject|train_compose",
  "pr_number": 42,
  "origin": "openspec",
  "strategy": "rebase",
  "backend": "coordinator_train|github_queue|direct",
  "duration_seconds": 12.5,
  "queue_depth": 7,
  "partition_count": 3,
  "train_id": "abc123",
  "success": true,
  "error": null
}
```

A formal JSON Schema for this event is deferred — the event is consumed only by the metrics aggregation script and the coordinator audit service, both in this same codebase. If external consumers need this schema, it should be extracted to `contracts/events/merge-event.schema.json`.

### Type Generation Stubs
**Not applicable.** No cross-language type generation needed. All consumers are Python.
