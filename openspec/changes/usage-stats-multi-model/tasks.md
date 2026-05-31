# Tasks — Multi-Model Usage Statistics Dashboard

Tasks are grouped by phase. Within each phase, test tasks precede the
implementation they verify (TDD). Sizes per the plan-feature Task Sizing
Reference. Checkpoint markers appear every 2–3 implementation tasks.

## Phase 0 — Contracts (wp-contracts)

- [ ] 0.1 (S) Validate `contracts/db/schema.sql`, `contracts/openapi/v1.yaml`,
  and generated stubs parse and cross-reference cleanly (lint OpenAPI, dry-run
  SQL).
  **Spec scenarios**: usage-api (Usage Query Endpoints), usage-collection (Normalized Usage Record)
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Dependencies**: None

## Phase 1 — Persistence + Collector core (Claude)

- [ ] 1.1 (S) Write migration test: applying `026_usage_stats.sql` creates
  `usage_records` + `usage_ingest_state` with the UNIQUE constraint and indexes.
  **Spec scenarios**: usage-collection (Incremental Idempotent Ingestion)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D3
  **Dependencies**: 0.1
- [ ] 1.2 (S) Create `agent-coordinator/database/migrations/026_usage_stats.sql`
  from the DB contract (table style mirrors existing migrations).
  **Design decisions**: D1, D3
  **Dependencies**: 1.1
- [ ] 1.3 (M) Write tests for `UsageRecord` schema + `record_hash` stability and
  the pricing table seeded from `agents.yaml` (known model → entry; unknown →
  None).
  **Spec scenarios**: usage-collection (Normalized Usage Record), usage-api (Pricing Seeded From Agent Registry)
  **Design decisions**: D2, D4
  **Dependencies**: 0.1
- [ ] 1.4 (M) Implement `collector/schema.py` (`UsageRecord` + `record_hash`) and
  `collector/pricing.py` (seed from `agents.yaml`).
  **Design decisions**: D2, D4
  **Dependencies**: 1.3
- [ ] Checkpoint: run migration + schema/pricing tests, review diff, verify scope
- [ ] 1.5 (M) Write tests for the Claude adapter against fixture JSONL
  transcripts (token mapping, model, session/project extraction).
  **Spec scenarios**: usage-collection (Claude transcript record normalized)
  **Design decisions**: D2
  **Dependencies**: 1.4
- [ ] 1.6 (M) Implement `collector/adapters/base.py` (adapter protocol +
  registry) and `collector/adapters/claude.py`.
  **Spec scenarios**: usage-collection (Vendor Adapter Isolation)
  **Design decisions**: D2
  **Dependencies**: 1.5
- [ ] 1.7 (M) Write tests for `collector/store.py`: incremental watermark resume,
  idempotent re-run inserts zero rows, offline spool + flush.
  **Spec scenarios**: usage-collection (Incremental Idempotent Ingestion, Session-End Ingestion with Offline Spool)
  **Design decisions**: D3, D5
  **Dependencies**: 1.2, 1.6
- [ ] 1.8 (M) Implement `collector/store.py` (watermark, dedupe, spool) and the
  coordinator push client.
  **Design decisions**: D3, D5
  **Dependencies**: 1.7
- [ ] Checkpoint: run collector test suite, review diff, verify scope

## Phase 2 — API + SSE

- [ ] 2.1 (M) Write API tests: `/usage/ingest` idempotent batch, `/usage/summary`
  / `/usage/daily` / `/usage/by-model` / `/usage/by-vendor` filtering, 401 on
  missing Bearer, `usage.recorded` SSE emission.
  **Spec scenarios**: usage-api (Usage Query Endpoints, Usage Ingestion Endpoint, Live Usage Event Stream)
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 1.2
- [ ] 2.2 (M) Implement `/usage/*` routes in `coordination_api.py` (reuse Bearer
  auth) backed by `db_postgres.py` queries.
  **Spec scenarios**: usage-api (Usage Query Endpoints, Usage Ingestion Endpoint)
  **Dependencies**: 2.1
- [ ] 2.3 (S) Wire `usage.recorded` SSE event via `coordinator_notify` on insert.
  **Spec scenarios**: usage-api (Live Usage Event Stream)
  **Dependencies**: 2.2
- [ ] Checkpoint: run API + SSE tests, review diff, verify scope

## Phase 3 — Frontend (apps/usage-stats)

- [ ] 3.1 (M) Scaffold `apps/usage-stats/` from the kanban-viz Vite/TS config;
  write `useUsage.ts` tests (SSE connect, polling fallback, filter→URL).
  **Spec scenarios**: usage-dashboard (Usage Dashboard Application, Per-Vendor and Per-Model Filtering)
  **Contracts**: contracts/generated/types.ts
  **Design decisions**: D6
  **Dependencies**: 2.2
- [ ] 3.2 (M) Implement `useUsage.ts` (Bearer fetch, SSE primary, polling
  fallback) and URL-encoded filter state.
  **Spec scenarios**: usage-dashboard (Usage Dashboard Application, Per-Vendor and Per-Model Filtering)
  **Design decisions**: D6
  **Dependencies**: 3.1
- [ ] 3.3 (M) Write component tests, then implement chart components
  (daily/weekly/all-time rollups, vendor/model filters, "n/a" cost labelling).
  **Spec scenarios**: usage-dashboard (Usage Dashboard Application, Estimated-Cost Labelling)
  **Dependencies**: 3.2
- [ ] Checkpoint: run frontend test suite, typecheck, review diff, verify scope

## Phase 4 — Session-end ingestion + remaining vendors

- [ ] 4.1 (S) Write a test that the session-end hook invokes the collector and
  tolerates an unreachable coordinator (spool, non-fatal exit).
  **Spec scenarios**: usage-collection (Session-End Ingestion with Offline Spool)
  **Design decisions**: D5
  **Dependencies**: 1.8
- [ ] 4.2 (S) Wire collector invocation into session-end (`skills/session-bootstrap`
  + `.claude`/`.codex`/`.gemini` hook configs).
  **Design decisions**: D5
  **Dependencies**: 4.1
- [ ] 4.3 (M) Write Codex adapter tests against fixture `rollout-*.jsonl`
  `token_count` events; implement `collector/adapters/codex.py`.
  **Spec scenarios**: usage-collection (Codex token_count event normalized)
  **Design decisions**: D2
  **Dependencies**: 1.6
- [ ] Checkpoint: run hook + Codex tests, review diff, verify scope
- [ ] 4.4 (M) Write Gemini adapter tests against fixture `telemetry.log` OTEL
  records; implement `collector/adapters/gemini.py` + the opt-in
  `.gemini/settings.json` telemetry setup step.
  **Spec scenarios**: usage-collection (Vendor Adapter Isolation)
  **Design decisions**: D2
  **Dependencies**: 1.6
- [ ] 4.5 (S) Implement `collector/adapters/antigravity.py` as an explicit
  unsupported stub (skipped-vendor warning, no abort).
  **Spec scenarios**: usage-collection (Antigravity adapter is an explicit unsupported stub)
  **Design decisions**: D2
  **Dependencies**: 1.6

## Phase 5 — Integration

- [ ] 5.1 (M) Merge packages; run full backend + frontend suites; end-to-end
  smoke (ingest fixtures → query API → render dashboard).
  **Dependencies**: 2.3, 3.3, 4.2, 4.3
- [ ] 5.2 (S) Document at `docs/usage-stats/README.md` (collector run, vendor
  coverage matrix, Gemini telemetry opt-in, pricing-table caveat).
  **Dependencies**: 5.1
- [ ] Checkpoint: full suite green, review cumulative diff, verify all scopes
