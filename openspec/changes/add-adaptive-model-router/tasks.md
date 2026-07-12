# Tasks: add-adaptive-model-router

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

- [ ] 2.1 Write integration tests for routing migrations — additive-only, idempotent re-apply [S]
  **Spec scenarios**: agent-coordinator.2
  **Contracts**: contracts/db/schema.sql
  **Dependencies**: 1.2
- [ ] 2.2 Create migration `00X_model_routing.sql` per DB contract [S]
  **Dependencies**: 2.1
- [ ] 2.3 Write tests for catalog service — CRUD, no-external-call read path, staleness flag [M]
  **Spec scenarios**: model-routing.1, model-routing.2
  **Design decisions**: D1, D4
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.4 Implement `src/model_routing/catalog.py` — catalog service over routing tables [M]
  **Dependencies**: 2.3
- [ ] 2.5 Write tests for OpenRouter refresher — price update, failure keeps rows, staleness [M]
  **Spec scenarios**: model-routing.2
  **Design decisions**: D4
  **Dependencies**: 2.4
- [ ] 2.6 Implement OpenRouter REST refresher with standing-key auth [M]
  **Dependencies**: 2.5
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.7 Write tests for local endpoint health probe — unhealthy exclusion, latency capture [S]
  **Spec scenarios**: model-routing.3
  **Design decisions**: D5
  **Dependencies**: 2.4
- [ ] 2.8 Implement local endpoint registration plus health probe [S]
  **Dependencies**: 2.7
- [ ] 2.9 Write tests for spend/counterfactual ledger — actual vs baseline, estimate labelling [M]
  **Spec scenarios**: model-routing.7, model-routing.8
  **Design decisions**: D7
  **Dependencies**: 2.2
- [ ] 2.10 Implement `src/model_routing/ledger.py` — spend accrual, counterfactual computation [M]
  **Dependencies**: 2.9
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.11 Wire refresher, probes, ledger rollup into WatchdogService schedules [S]
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
- [ ] 3.4 Implement Cedar feasibility policies plus vendor attribute schema [M]
  **Spec scenarios**: model-routing.5
  **Dependencies**: 3.3
- [x] 3.5 Write tests for exploration budget — dual ceilings, premium ineligibility, provenance flag [M]
  **Spec scenarios**: model-routing.6
  **Design decisions**: D6
  **Dependencies**: 3.2
- [x] 3.6 Implement exploration selection under pct plus monthly-USD ceilings [M]
  **Dependencies**: 3.5
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.7 Write tests for routing API endpoints plus MCP tool parity [M]
  **Spec scenarios**: agent-coordinator.1
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 3.2
- [ ] 3.8 Expose resolver via HTTP endpoints plus MCP tool [M]
  **Dependencies**: 3.7
- [ ] 3.9 Write tests for archetype delegation — flag off equals static result; timeout fallback signal [M]
  **Spec scenarios**: agent-archetypes.1, model-routing.14
  **Design decisions**: D2
  **Dependencies**: 3.8
- [ ] 3.10 Implement `ROUTING_ADAPTIVE` delegation in `agents_config.resolve_archetype_for_phase` [S]
  **Dependencies**: 3.9
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.11 Add `endpoint_kind`/`base_url` fields to agents.yaml schema with validation [S]
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
- [ ] 4.6 Enforce exploration gating in roadmap dispatch path [S]
  **Dependencies**: 4.5
- [ ] Checkpoint: run tests, review diff, verify scope

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
- [ ] 5.4 Wire learning-log writers to POST `/routing/feedback` (best-effort, non-blocking) [S]
  **Dependencies**: 5.3
- [ ] 5.5 Write tests for gen-eval calibration seeding of local-model priors [S]
  **Spec scenarios**: model-routing.3
  **Design decisions**: D5
  **Dependencies**: 5.2
- [ ] 5.6 Implement gen-eval calibration suite runner seeding local priors [M]
  **Dependencies**: 5.5
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Probes, tripwires (wp-probes)

- [ ] 6.1 Write tests for ToS monitor — hash diff emits signal, vendor freeze until ack [S]
  **Spec scenarios**: model-routing.11
  **Design decisions**: D11
  **Dependencies**: 2.11
- [ ] 6.2 Implement ToS monitor probe [S]
  **Dependencies**: 6.1
- [ ] 6.3 Write tests for model canary — fingerprint drift invalidates posteriors [S]
  **Spec scenarios**: model-routing.12
  **Dependencies**: 2.11
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 6.4 Implement model canary probe [S]
  **Dependencies**: 6.3
- [ ] 6.5 Write tests for tripwire evaluation — economic kill, posture-flip signals [M]
  **Spec scenarios**: model-routing.13
  **Dependencies**: 6.2, 6.4
- [ ] 6.7 Write tests for quota probe — quota-axi JSON normalized to signal, resilience down-rank, graceful degrade [S]
  **Spec scenarios**: model-routing.15
  **Design decisions**: D13
  **Dependencies**: 2.11
- [ ] 6.8 Implement optional quota probe (quota-axi subprocess adapter, off by default) [S]
  **Dependencies**: 6.7
- [ ] 6.6 Implement tripwire evaluator with posture flips as signals [M]
  **Dependencies**: 6.5
- [ ] Checkpoint: run tests, review diff, verify scope, verify quota probe degrades cleanly

## Phase 7 — Dashboard (wp-dashboard)

- [ ] 7.1 Write component tests for usage dashboard — scoreboard render, estimate labelling [M]
  **Spec scenarios**: observability.1
  **Design decisions**: D12
  **Dependencies**: 1.1
- [ ] 7.2 Scaffold `apps/usage-viz` from kanban-viz conventions (auth, SSE/poll hooks) [M]
  **Dependencies**: 7.1
- [ ] 7.3 Implement spend, savings, scoreboard, exploration burn-down views [M]
  **Dependencies**: 7.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 7.4 Write tests for routing telemetry emission — fallback label present [S]
  **Spec scenarios**: observability.2
  **Dependencies**: 3.10
- [ ] 7.5 Emit routing OTel measurements on `coordinator.signal` meter [S]
  **Dependencies**: 7.4

## Phase 8 — Integration, archival (wp-integration)

- [ ] 8.1 Run full test suite across coordinator plus skills venvs [S]
  **Dependencies**: all prior phases
- [ ] 8.2 E2E: flag-on routed quick-task to local endpoint; flag-off parity check [M]
  **Spec scenarios**: model-routing.14, agent-archetypes.1
  **Dependencies**: 8.1
- [ ] 8.3 Archive absorbed changes with superseded-by pointers (`cross-vendor-arbitrage-instrument`, `usage-stats-multi-model`) [XS]
  **Design decisions**: Absorption mechanics
  **Dependencies**: 8.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 8.4 Register OpenRouter MCP server in `.mcp.json` as dev-time tool with setup docs [XS]
  **Design decisions**: D4
  **Dependencies**: None
- [ ] 8.5 Write ADR for adaptive routing placement plus objective-profile semantics [S]
  **Design decisions**: D1, D3
  **Dependencies**: 8.2
