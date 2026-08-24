# Contracts: agentic-flow-display

Planned artifacts, generated during implementation (Phase 1/3), not
hand-authored ahead of it:

- `flow-fact.schema.json` — JSON Schema generated from the extended
  `NormalizedEvent` dataclasses
  (`skills/collect-transcripts/scripts/normalize.py`), the wire shape of
  `GET /flows/sessions/{id}/events` items. Single source of truth for
  hook emission, batch upload, transcript JSONL, and the flow-viz fold's
  input type.
- `flow-session-summary.schema.json` — generated from `SessionSummary`
  plus `source` (`transcript | langfuse`) and `source_warnings`, the
  wire shape of `GET /flows/sessions` items.

Invariants the contracts must encode:

- `sequence_number` strictly orders events within a session.
- `tool_use_id` pairs `tool_use` and `tool_result` content blocks.
- `spawned_by_tool_use_id` references a `tool_use_id` in the parent
  session's stream; absence of linkage fields is valid (single-node
  degradation).
- All fields survive sanitization; no secret-bearing field exists in the
  contract.
