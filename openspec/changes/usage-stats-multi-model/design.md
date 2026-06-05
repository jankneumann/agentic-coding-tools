# Design — Multi-Model Usage Statistics Dashboard

## Context

Reuse the coordinator's Postgres + FastAPI + (kanban-viz) React stack to build a
fleet-wide, multi-vendor usage dashboard. Reference prior art:
`phuryn/claude-usage` (Claude JSONL → SQLite → Chart.js). This design keeps that
tool's *parsing* insight (passively read locally-written transcripts) but
replaces its *storage/serving* (SQLite + http.server) with the coordinator.

## Goals / Non-Goals

**Goals:** normalized multi-vendor records; fleet aggregation; incremental
idempotent ingestion; kanban-viz-consistent dashboard; cheap vendor extension.

**Non-Goals:** billing-accurate cost (estimates only); capturing server-side
"cowork" sessions that write no local transcript; supporting Antigravity beyond
a stub until a local-log contract is confirmed.

## Decisions

### D1: Coordinator Postgres over SQLite

Reuse `agent-coordinator` Postgres via migration `026_usage_stats.sql`. SQLite
(claude-usage's choice) is rejected: it cannot do fleet-wide aggregation (the
operator's selected scope) and duplicates migration/query machinery the repo
already has. **Trade-off accepted:** collector requires network + API key;
mitigated by D6 offline spool.

### D2: Vendor-adapter core with a normalized `UsageRecord`

One adapter per vendor behind `discover_files()` / `iter_records()`. Storage,
pricing, API, and UI operate only on `UsageRecord`. Adding a vendor = one file.
Gemini's OTEL paradigm is thereby quarantined to `adapters/gemini.py` rather
than shaping the pipeline (the reason Approach 3 / OTEL-native was rejected).

### D3: Idempotency on `(vendor, session_id, record_hash)` + per-file watermark

`record_hash` = stable hash of the normalized record's identifying fields.
`usage_ingest_state` stores `(file_path, mtime, byte_offset)` so re-runs resume
rather than re-parse. A DB UNIQUE constraint makes ingestion idempotent even if
the watermark is lost. This is the Postgres translation of claude-usage's
mtime-map + scan-incremental approach.

### D4: Pricing seeded from `agents.yaml`

The pricing table's known-model set is generated from `agents.yaml`
(`model` + `model_fallbacks`) — the same registry `vendor_health.py` reads —
so configured models always have a price entry (rate or explicit "unknown").
Unknown models persist with `cost_usd = NULL` and render "n/a". Costs are always
labelled estimates (Pro/Max subscribers don't pay per-token).

### D5: Ingestion at session end with offline spool

A session-end hook invokes the collector (wired via `skills/session-bootstrap`
and the `.claude`/`.codex`/`.gemini` hook configs). On coordinator failure the
collector writes a local spool file and exits non-fatally; the next run flushes
it. Chosen over a daemon (no new long-running process) and over manual CLI
(can't be forgotten). A manual `collect` entrypoint remains for backfill.

### D6: Dashboard mirrors `useCoordinator.ts`

`useUsage.ts` copies the kanban-viz hook shape: Bearer fetch, SSE primary
(`usage.recorded`), polling fallback. Filters are URL-encoded for bookmarkable
views.

## Risks / Trade-offs

- **Coordinator coupling** (D1) — offline spool (D5) bounds data-loss risk.
- **Gemini telemetry is opt-in** — Phase 3 ships a setup step that writes the
  `.gemini/settings.json` telemetry config; without it the Gemini adapter emits
  nothing (documented, not silently broken).
- **Cost accuracy** — explicitly estimates; rates live in one seam (D4) for easy
  correction.

## Migration / Rollout

Phased by vendor adapter (Claude → Codex → Gemini → Antigravity stub). The
migration, API, and frontend ship in Phase 1 with Claude; later phases add only
adapter files + (Gemini) a telemetry setup step. No existing coordinator table
or route is modified — purely additive.
