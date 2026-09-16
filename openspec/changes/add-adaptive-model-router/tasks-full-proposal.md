# Tasks: add-adaptive-model-router

> **dg-00 execution boundary (2026-09-16):** This task record tracks the
> roadmap item wiring tranche. The broader original-router backlog remains in
> `deferred-tasks.md`; it is not claimed as delivered by dg-00.

Sizes: XS/S/M per plan-feature sizing. No XL; single flagged L decomposed internally (see
design.md "Task-sizing notes"). Scenario IDs are `<capability>.<requirement-ordinal>`.

## Phase 1 — Contracts (wp-contracts)

- [x] 1.1 Write OpenAPI contract for routing endpoints (`/routing/select_model`, `/routing/catalog`, `/routing/decisions/{id}`, `/routing/usage`, `/routing/feedback`) [S]
  **Spec scenarios**: agent-coordinator.1
  **Design decisions**: D1
  **Dependencies**: None
- [x] 1.2 Write DB contract for routing tables (`model_catalog`, `model_posteriors`, `routing_decisions`, `routing_spend_ledger`) [S]
  **Spec scenarios**: agent-coordinator.2
  **Design decisions**: D8
  **Dependencies**: None
- [x] 1.3 Write event contract for routing signal payloads (decision, fallback, tripwire, probe) [S]
  **Spec scenarios**: model-routing.10
  **Design decisions**: D8
  **Dependencies**: None
- [x] Checkpoint: run contract lint/validation, review diff, verify scope
- [x] 1.4 Generate Pydantic models from OpenAPI schemas into `contracts/generated/` [XS]
  **Dependencies**: 1.1, 1.2, 1.3

## Phase 2 — Catalog storage layer (wp-db-catalog) [flagged L, decomposed]

- [x] 2.1 Write integration tests for routing migrations — additive-only, idempotent re-apply [S]
  **Spec scenarios**: agent-coordinator.2
  **Contracts**: contracts/db/schema.sql
  **Dependencies**: 1.2
- [x] 2.2 Create migration `00X_model_routing.sql` per DB contract [S]
  **Dependencies**: 2.1
- [x] 2.3 Write tests for catalog service — CRUD, no-external-call read path, staleness flag [M]
  **Spec scenarios**: model-routing.1, model-routing.2
  **Design decisions**: D1, D4
  **Dependencies**: 2.2
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.4 Implement `src/model_routing/catalog.py` — catalog service over routing tables [M]
  **Dependencies**: 2.3
- [x] 2.5 Write tests for OpenRouter refresher — price update, failure keeps rows, staleness [M]
  **Spec scenarios**: model-routing.2
  **Design decisions**: D4
  **Dependencies**: 2.4
- [x] 2.6 Implement OpenRouter REST refresher with standing-key auth [M]
  **Dependencies**: 2.5
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.7 Write tests for local endpoint health probe — unhealthy exclusion, latency capture [S]
  **Spec scenarios**: model-routing.3
  **Design decisions**: D5
  **Dependencies**: 2.4
- [x] 2.8 Implement local endpoint registration plus health probe [S]
  **Dependencies**: 2.7
- [x] 2.9 Write tests for spend/counterfactual ledger — actual vs baseline, estimate labelling [M]
  **Spec scenarios**: model-routing.7, model-routing.8
  **Design decisions**: D7
  **Dependencies**: 2.2
- [x] 2.10 Implement `src/model_routing/ledger.py` — spend accrual, counterfactual computation [M]
  **Dependencies**: 2.9
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.11 Wire refresher, probes, ledger rollup into WatchdogService schedules [S]
  **Spec scenarios**: agent-coordinator.3
  **Dependencies**: 2.6, 2.8, 2.10

## Phase 3 — Selection resolver (wp-resolver)

- [x] 3.1 Write tests for scoring — prior/posterior blend, profile weight changes, provenance content [M]
  **Spec scenarios**: model-routing.4, model-routing.10
  **Design decisions**: D3
  **Dependencies**: 1.4
- [x] 3.2 Implement `src/model_routing/resolver.py` — linear utility ranking with objective profiles [M]
  **Dependencies**: 3.1
- [x] 3.3 Write tests for Cedar hard constraints — EULA ineligibility excluded pre-scoring [S]
  **Spec scenarios**: model-routing.5
  **Design decisions**: D10
  **Dependencies**: 3.2
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.5 Write tests for exploration budget — dual ceilings, premium ineligibility, provenance flag [M]
  **Spec scenarios**: model-routing.6
  **Design decisions**: D6
  **Dependencies**: 3.2
- [x] 3.6 Implement exploration selection under pct plus monthly-USD ceilings [M]
  **Dependencies**: 3.5
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.7 Write tests for routing API endpoints plus MCP tool parity [M]
  **Spec scenarios**: agent-coordinator.1
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 3.2
- [x] 3.8 Expose resolver via HTTP endpoints plus MCP tool [M]
  **Dependencies**: 3.7
- [x] 3.9 Write tests for archetype delegation — flag off equals static result; timeout fallback signal [M]
  **Spec scenarios**: agent-archetypes.1, model-routing.14
  **Design decisions**: D2
  **Dependencies**: 3.8
- [x] 3.10 Implement `ROUTING_ADAPTIVE` delegation in `agents_config.resolve_archetype_for_phase` [S]
  **Dependencies**: 3.9
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.11 Add `endpoint_kind`/`base_url` fields to agents.yaml schema with validation [S]
  **Spec scenarios**: agent-archetypes.2
  **Dependencies**: 3.10

## Phase 4 — Dispatch adapter, policy pricing (wp-dispatch)

- [x] 4.1 Write tests for OpenAI-compatible adapter — OpenRouter headers, generation-id capture, local base_url [M]
  **Spec scenarios**: model-routing.7
  **Design decisions**: D10
  **Dependencies**: 1.4
- [x] 4.2 Implement `OpenAICompatAdapter` in review_dispatcher (tier-2.5 discovery order) [M]
  **Dependencies**: 4.1
- [x] 4.3 Write tests for policy cost model — catalog-priced deltas, static fallback labelling [S]
  **Spec scenarios**: roadmap-orchestration.1
  **Design decisions**: D7
  **Dependencies**: 1.4
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 4.4 Replace `_estimate_cost_delta` stub with catalog-priced estimation [S]
  **Dependencies**: 4.3
- [x] 4.5 Write tests for roadmap exploration gating — fail-closed items never explored [S]
  **Spec scenarios**: roadmap-orchestration.2
  **Dependencies**: 4.4
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Feedback aggregation (wp-feedback)

- [x] 5.1 Write tests for posterior aggregation — source weights, decay, sample-size confidence [M]
  **Spec scenarios**: model-routing.9
  **Design decisions**: D9
  **Dependencies**: 1.4
- [x] 5.2 Implement `src/model_routing/feedback.py` aggregation job over four sources [M]
  **Dependencies**: 5.1
- [x] 5.3 Write tests for VendorSwitch/vendor_notes ingestion from roadmap workspaces [S]
  **Spec scenarios**: model-routing.9
  **Dependencies**: 5.2
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 8 — Integrated review and validation (wp-integration)

- [ ] 8.1 Run the full affected coordinator and skills test suites [S]
  **Dependencies**: all implemented dg-00 tasks
- [ ] 8.2 Complete multi-vendor plan and implementation review, strict OpenSpec validation, and architecture checks [S]
  **Dependencies**: 8.1
