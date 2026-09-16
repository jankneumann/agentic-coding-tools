# Change Context: add-adaptive-model-router (dg-00)

Canonical traceability for dispatch-governance item dg-00. The original full-proposal matrix
is preserved in `change-context-full-proposal.md`; deferred normative text is preserved under
`deferred-specs/` and indexed by `deferred-tasks.md`.

## Requirement Traceability Matrix

| Req | Requirement | Contract | Design | Tests | Implementation | Status |
|---|---|---|---|---|---|---|
| agent-coordinator.1 | Five HTTP paths plus MCP selection parity | `contracts/openapi/v1.yaml` | D1 | `test_api.py`, `test_service.py` | `model_routing/api.py`, `coordination_api.py`, `coordination_mcp.py`, `http_proxy.py` | verified |
| agent-coordinator.2 | Additive, idempotent routing migration | `contracts/db/schema.sql` | D8 | `test_fresh_database_migration.py`, `test_migrations_catalog.py` | `040_model_routing.sql` | verified |
| agent-coordinator.3 | Independent refresher/probe/ledger watchdog jobs | — | D4 | `test_catalog_watchdog.py`, `test_watchdog.py` | `watchdog.py` | verified |
| agent-archetypes.1 | Signal forwarding plus default-off adaptive delegation with exact bounded fallback | — | D2 | `test_delegation.py`, `test_coordination_api.py` | `agents_config.py`, `coordination_api.py` | verified |
| agent-archetypes.2 | Endpoint metadata accepted, serialized, and registered for probing | — | D5 | `test_agent_endpoints.py`, `test_local_endpoints.py` | `agents_config.py`, `model_routing/local_endpoints.py` | verified |
| model-routing.1 | Storage-only catalog CRUD and staleness | `contracts/db/schema.sql#model_catalog` | D1 | `test_catalog.py` | `model_routing/catalog.py` | verified |
| model-routing.2 | Refresh updates and failure preservation | `contracts/openapi/v1.yaml#/paths/~1routing~1catalog` | D4 | `test_refresher.py` | `model_routing/refresher.py` | verified |
| model-routing.3 | Local endpoint registration and health exclusion | `contracts/db/schema.sql#model_catalog` | D5 | `test_local_endpoints.py` | `model_routing/local_endpoints.py` | verified |
| model-routing.4 | Resolver transport surface and durable decisions | `contracts/openapi/v1.yaml#/paths/~1routing~1select_model` | D3 | `test_api.py`, `test_service.py` | `model_routing/api.py` | verified |
| model-routing.5 | Actual/counterfactual ledger with estimate labels | `contracts/db/schema.sql#routing_spend_ledger` | D7 | `test_ledger.py` | `model_routing/ledger.py` | verified |
| model-routing.6 | Static-tier kill switch and timeout fallback | — | D2 | `test_delegation.py` | `agents_config.py` | verified |
| parallel-infrastructure.1 | OpenAI-compatible adapter reachable in discovery order | — | D10 | `test_review_dispatcher.py` | `review_dispatcher.py` | verified |

## Coverage Summary

- Canonical dg-00 requirements: 12 verified, 0 pending.
- Roadmap acceptance outcomes: 4 have focused implementation evidence; final acceptance sign-off
  remains pending tasks 8.1–8.2 (combined validation and implementation-review convergence).
- Canonical packages: wp-contracts, wp-db-catalog, wp-resolver, wp-dispatch, wp-integration.
- Deferred full-proposal areas: Cedar deployment, roadmap exploration enforcement, feedback
  producers/calibration, ToS/canary/tripwire/quota probes, dashboard/telemetry, and archival/docs.
- Extensibility guard: no central model-ownership migration and no ri-18 billing fields were
  added to `CandidateInput`; both remain compatible future work.
