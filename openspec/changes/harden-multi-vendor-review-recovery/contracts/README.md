# Contracts — harden-multi-vendor-review-recovery

This change introduces no HTTP API, no database schema changes, and no pub/sub events. The only contracted interface is the **on-disk checkpoint format** that the in-process `converge()` API writes (newly) and the existing `review_dispatcher.py` writes (after migration via the shared helper).

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints introduced or modified. |
| Database | No | No schema changes. No new tables. |
| Events | No | The `convergence.synthesis_failed_with_checkpoint` and `convergence.checkpoint_write_failed` markers in this proposal are **structured-log entries** emitted via Python's `logging` module, NOT pub/sub events or coordinator audit events. There is no message bus, no HTTP audit endpoint, and no new coordination_bridge helper introduced by this proposal. |
| File format / on-disk schema | **Yes** | The `.review-cache/` directory layout (and the existing `<output_dir>/findings-*-{review_type}.json` layout the CLI dispatcher writes today) is the coordination boundary between the in-process flow and the existing CLI synthesizer. They must agree on the format. |

## Files in this directory

- [`review-cache-layout.schema.json`](review-cache-layout.schema.json) — JSON Schema for `review-manifest.json`. Superset of the existing `review_dispatcher.py:write_manifest()` shape — preserves `review_type`, `target`, `dispatches[]`, `quorum_requested`, `quorum_received` AND adds `schema_version`, `change_id` (optional, may be null), `created_at`, `vendors[]`. Existing CLI consumers continue working unchanged.
- [`finding.schema.json`](finding.schema.json) — JSON Schema for `findings-{vendor}-{review_type}.json` files. Documents the EXISTING wire format (wrapper object `{review_type, target, reviewer_vendor, findings: [...]}`), NOT a new shape. The schema's `criticality` enum is `[low, medium, high, critical]` — matches the existing `openspec/schemas/review-findings.schema.json` and the `consensus_synthesizer.py` ranking logic.

## Why these are contracts

The shared helper (`checkpoint_findings.py`) is the only writer; readers include the existing `consensus_synthesizer.py` (no changes in this proposal) and the new in-process `converge()` flow. Centralizing the format in a versioned JSON Schema means a future modification can bump `schema_version` and readers can refuse unknown versions — a structured boundary instead of silent miscompute.

## Schema version

The manifest schema declares `schema_version: 1`. Future changes to the manifest format MUST bump this version. Readers SHALL refuse manifests with unknown `schema_version` and emit a clear error.

The per-vendor finding-file schema does NOT carry a `schema_version` field — its shape is fixed by the existing wire format that the synthesizer reads via `data.get("findings", [])`. Tightening or restructuring that file is a separate proposal.

## Legacy manifests

Manifests written by older versions of `review_dispatcher.py` (before this proposal lands) lack `schema_version`, `change_id`, `created_at`, `vendors[]`. They DO NOT validate against this schema. Operators wanting to inspect them should treat them as a separate (un-versioned) format. After this proposal lands, all newly-written manifests carry the new fields; legacy `.review-cache/` directories from prior runs will be regenerated next time the dispatcher writes to them.
