# Change Context: add-adaptive-model-router

Traceability skeleton generated at implementation start (Phase 1). Requirement IDs are
`<capability>.<n>` in spec order. Contract refs point at `contracts/`; design refs at `design.md`.

## dg-00 Roadmap Acceptance Traceability (2026-09-16)

This recovery executes only the four dg-00 wiring outcomes. The original full-proposal
matrix below remains as historical scope accounting; rows labeled pending there are not claimed
as delivered and are preserved in `deferred-tasks.md`.

| dg-00 outcome | Implementation | Tests | Status |
|---|---|---|---|
| Five `/routing/*` OpenAPI paths and matching MCP selection tool | `src/model_routing/api.py`, `src/coordination_api.py`, `src/coordination_mcp.py`, `src/http_proxy.py` | `test_api.py`, `test_service.py` | verified |
| Additive routing migration plus storage-only catalog reads | `database/migrations/040_model_routing.sql`, `src/model_routing/catalog.py` | `test_fresh_database_migration.py`, `test_migrations_catalog.py`, `test_catalog.py` | verified |
| Adaptive flag off preserves exact static result; on delegates with bounded fallback | `src/agents_config.py` | `test_delegation.py`, `test_agent_endpoints.py` | verified |
| OpenAI-compatible adapter reachable in dispatcher discovery order | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_review_dispatcher.py` | verified |

## Original Full-Proposal Requirement Matrix (not a dg-00 completion claim)

| Req | Requirement (short) | Contract Ref | Design | Test | Files Changed | Status |
|-----|--------------------|--------------|--------|------|---------------|--------|
| model-routing.1 | Model Catalog | contracts/db/schema.sql#model_catalog | D1 | test_catalog | --- | pending |
| model-routing.2 | OpenRouter Catalog Refresher | contracts/openapi/v1.yaml#/routing/catalog | D4 | test_refresher | --- | pending |
| model-routing.3 | Local Endpoint Registration | contracts/db/schema.sql#model_catalog | D5 | test_local_endpoints | --- | pending |
| model-routing.4 | Adaptive Selection Resolver | contracts/openapi/v1.yaml#/routing/select_model | D3 | test_resolver | src/model_routing/resolver.py | core (API pending) |
| model-routing.5 | Hard Feasibility Constraints (Cedar) | --- | D10 | test_resolver | src/model_routing/resolver.py | filter done (Cedar policy pending) |
| model-routing.6 | Exploration Budget | contracts/openapi/v1.yaml#SelectModelRequest | D6 | test_resolver | src/model_routing/exploration.py | verified |
| model-routing.7 | Monthly Metered Spend Ceiling | contracts/db/schema.sql#routing_spend_ledger | D7 | test_ledger | --- | pending |
| model-routing.8 | Metered-Counterfactual Cost Ledger | contracts/db/schema.sql#routing_spend_ledger | D7 | test_ledger | --- | pending |
| model-routing.9 | Feedback Posterior Aggregation | contracts/openapi/v1.yaml#FeedbackEvent | D9 | test_feedback | src/model_routing/feedback.py | core+normalizers done (HTTP wiring pending) |
| model-routing.10 | Signal Recording + Decision Provenance | contracts/events/routing-signal.schema.json | D8 | test_provenance | --- | pending |
| model-routing.11 | ToS Monitor Probe | contracts/events/routing-signal.schema.json | D11 | test_probes | --- | pending |
| model-routing.12 | Model Canary Probe | contracts/events/routing-signal.schema.json | D11 | test_probes | --- | pending |
| model-routing.13 | Tripwires Flip Posture | contracts/events/routing-signal.schema.json | D11 | test_tripwires | --- | pending |
| model-routing.14 | Static-Tier Fallback + Kill Switch | --- | D2 | test_delegation | --- | pending |
| model-routing.15 | Proactive Quota Headroom Signal | contracts/db/schema.sql#model_catalog | D13 | test_quota | --- | pending |
| agent-coordinator.1 | Model Routing API Surface | contracts/openapi/v1.yaml | D1 | test_api | --- | pending |
| agent-coordinator.2 | Routing Storage Migrations | contracts/db/schema.sql | D8 | test_migrations | --- | pending |
| agent-coordinator.3 | Routing Watchdog Jobs | --- | D4,D11 | test_watchdog | --- | pending |
| agent-archetypes.1 | Archetype Resolution Delegates to Router | --- | D2 | test_delegation | --- | pending |
| agent-archetypes.2 | Endpoint Kind in Agent Registry | --- | D5 | test_agents_config | --- | pending |
| roadmap-orchestration.1 | Policy Engine Uses Catalog Pricing | --- | D7 | test_routing_policy | skills/autopilot-roadmap/scripts/policy.py | verified |
| roadmap-orchestration.2 | Exploration Budget Enforcement in Roadmap | --- | D6 | test_routing_policy | skills/autopilot-roadmap/scripts/policy.py | gate done (orchestrator wiring pending) |
| observability.1 | Usage and Routing Dashboard | contracts/openapi/v1.yaml#/routing/usage | D12 | usage-viz tests | --- | pending |
| observability.2 | Routing Telemetry | --- | D8 | test_telemetry | --- | pending |

## Design Decision Trace

D1 placement · D2 fallback flag · D3 scoring (cost-per-completed-task posterior, rev2) ·
D4 refresher standing-key · D5 local endpoints · D6 exploration dual-ceiling · D7 spend ceiling ·
D8 signal placement · D9 feedback weights (deterministic > LLM-judged, rev2) · D10 dispatch adapter ·
D11 probes/tripwires · D12 dashboard (cost-per-completed-task headline, rev2).

## Original Planning Snapshot

- Requirements: 23 total, 1 verified (exploration), 3 core-complete (resolver/feasibility), 19 pending
- Contracts: OpenAPI (5 paths), DB (4 tables), events (1 schema) — all present, parse-validated
- Package status: wp-contracts in progress; wp-db-catalog … wp-integration pending
