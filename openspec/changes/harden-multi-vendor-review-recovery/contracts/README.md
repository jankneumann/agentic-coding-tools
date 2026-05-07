# Contracts — harden-multi-vendor-review-recovery

This change introduces no HTTP API, no database schema changes, and no events. The only contracted interface is the **on-disk checkpoint format** that both the in-process `converge()` API and the `consensus_synthesizer.py` CLI subprocess read and write.

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints introduced or modified. |
| Database | No | No schema changes; no new tables. The audit-log events use the existing audit table schema. |
| Events | No | The `convergence.fallback_recovered` and `convergence.fallback_failed` audit log entries are not pub/sub events; they're append-only audit rows using the existing audit envelope. |
| File format / on-disk schema | **Yes** | The `.review-cache/` directory layout is the coordination boundary between the in-process synthesizer and the CLI subprocess fallback. Both must agree on the format byte-for-byte. |

## Files in this directory

- [`review-cache-layout.schema.json`](review-cache-layout.schema.json) — JSON Schema for `.review-cache/review-manifest.json`. Validates manifest structure, vendor entries, schema_version.
- [`finding.schema.json`](finding.schema.json) — JSON Schema for individual `findings-{vendor}-{review_type}.json` entries. Validates finding shape (id, type, criticality, description, disposition, file_path, line_range, vendor).

## Why these are contracts, not just internal types

The two callers — `convergence_loop.py:converge()` writes the files; `consensus_synthesizer.py` reads them via `subprocess` invocation — are coordinated **only** via the on-disk format. There is no shared in-memory type. If one side changes the layout without updating the other, the recovery path silently breaks (subprocess succeeds but its parse fails, or worse, parses wrong data). Treating the layout as a versioned schema with `schema_version: int` lets either side detect mismatch and refuse rather than corrupting.

## Schema version

Both schemas declare `schema_version: 1`. Future changes to the on-disk layout MUST bump this version. The CLI's manifest reader SHALL refuse manifests with unknown `schema_version` and emit a clear error so the fallback path's failure mode is "explicit refusal" rather than "silent miscompute."
