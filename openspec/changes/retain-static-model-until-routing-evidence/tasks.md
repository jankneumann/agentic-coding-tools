# Tasks: Retain the static model until routing evidence exists

> Change ID: `retain-static-model-until-routing-evidence`
> Tier: sequential (single `wp-main` package)
> Scenario IDs: `model-routing.1`–`.9` are the scenarios of "Incumbent Retention Until Routing
> Evidence", in order. `agent-archetypes.1`–`.6` are the scenarios of "Archetype Resolution
> Delegates to Adaptive Router", in order (4–6 are new).

## 1. Contracts

- [x] 1.1 Write failing contract tests for the v1.2 overlay: optional `incumbent` on the request,
  optional `retention` on the response, `selected` nullable only alongside `retention.retained`,
  and the decision-record schema accepting `retention`. Resolve paths with `change_dir()`. [S]
  **Spec scenarios**: model-routing.5, model-routing.7, model-routing.9
  **Contracts**: contracts/openapi/v1.2.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D5, D7
  **Dependencies**: None
- [x] 1.2 Finalize `contracts/openapi/v1.2.yaml`, the decision-record schema and
  `contracts/generated/models.py` so that 1.1 passes. [S]
  **Dependencies**: 1.1

## 2. Evidence predicate and retention core

- [x] 2.1 Write failing resolver tests for `has_evidence`: samples only, prior only, both, and
  neither. [XS]
  **Spec scenarios**: model-routing.1
  **Design decisions**: D1
  **Dependencies**: None
- [x] 2.2 Implement `has_evidence(candidate)` in `model_routing/resolver.py`. [XS]
  **Dependencies**: 2.1
- [x] 2.3 Write failing tests for the pure `apply_incumbent_retention(ranked, excluded,
  incumbent, margin)`, covering every row of the D3 table: no evidence, below margin, above margin,
  exact tie at margin 0, unresolved, infeasible with and without an evidenced alternative, and duplicate
  `(vendor, model)` rows taking the maximum score. [S]
  **Spec scenarios**: model-routing.1, model-routing.2, model-routing.3, model-routing.4,
  model-routing.5, model-routing.6, model-routing.7
  **Design decisions**: D2, D3
  **Dependencies**: 2.2
- [x] 2.4 Implement `apply_incumbent_retention` in `model_routing/resolver.py`. [S]
  **Dependencies**: 2.3
- [x] Checkpoint: run `tests/model_routing/`, review the diff, and confirm only contracts and resolver.py changed.

## 3. Exploration gating

- [ ] 3.1 Write failing tests: with an incumbent and fewer than 2 evidenced candidates, exploration
  never fires across many seeded draws. With 2 or more evidenced candidates, every explored pick is
  evidenced and has reason `exploration-evidenced`. Without an incumbent, `choose()` output is
  unchanged for a fixed seed. [S]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Design decisions**: D4
  **Dependencies**: 2.4
- [ ] 3.2 Add an evidenced-only exploration pool to the `choose()` call path in
  `model_routing/exploration.py`, without changing it when no incumbent is present. [S]
  **Dependencies**: 3.1

## 4. Service and API surface

- [ ] 4.1 Write failing service and API tests: `SelectModelRequest.incumbent` is accepted, and
  `ROUTING_INCUMBENT_MARGIN` is read with default 0.05 and rejected when negative. The response
  carries `retention` only when an incumbent is supplied, and the persisted decision row includes
  `retention` and validates against the v1.2 decision-record schema. A null `selected` is persisted
  for unresolved incumbents. [M]
  **Spec scenarios**: model-routing.1, model-routing.5, model-routing.7, model-routing.9
  **Contracts**: contracts/openapi/v1.2.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D3, D5
  **Dependencies**: 3.2, 1.2
- [ ] 4.2 Wire retention into `RoutingService.select_model` in `model_routing/api.py`: request
  field, margin knob, retention step, `retention` payload, nullable `selected`, and decision
  persistence on both the plain and assignment paths. [M]
  **Dependencies**: 4.1
- [ ] 4.3 Write failing MCP and HTTP parity tests for `incumbent` on `select_model_for_task`
  (`coordination_mcp.py`) and `proxy_select_model_for_task` (`http_proxy.py`). [S]
  **Spec scenarios**: model-routing.1
  **Dependencies**: 4.2
- [ ] 4.4 Add the `incumbent` parameter to the MCP tool and the HTTP proxy. [S]
  **Dependencies**: 4.3
- [ ] 4.5 Write a failing static test for migration 044: it adds nullable `retention`, drops
  NOT NULL on `selected` behind the `selected IS NOT NULL OR retention IS NOT NULL` CHECK, and
  replaces `record_routing_decision_with_audit` to insert `retention` with the COALESCE'd
  policy fields. [XS]
  **Spec scenarios**: model-routing.5, model-routing.7
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D8
  **Dependencies**: 4.2
- [ ] 4.6 Write `database/migrations/044_routing_decision_retention.sql`. [S]
  **Dependencies**: 4.5
- [ ] 4.7 Write failing `CatalogService.record_decision_and_audit` tests for a null `selected`:
  the audit link has a null agent and model and takes its policy fields from the top-level
  `provenance`. [XS]
  **Spec scenarios**: model-routing.5, model-routing.7
  **Design decisions**: D8
  **Dependencies**: 4.6
- [ ] 4.8 Handle a null `selected` in `record_decision_and_audit` (`model_routing/catalog.py`). [XS]
  **Dependencies**: 4.7
- [ ] Checkpoint: run `tests/model_routing/` plus the MCP parity tests, and confirm the diff stays inside `model_routing/`, `coordination_mcp.py`, `http_proxy.py`, migration 044 and contracts.

## 5. Client delegation

- [ ] 5.1 Write failing delegation tests in `tests/model_routing/test_delegation.py`: the incumbent
  is forwarded with `catalog_vendor` (including pi → `openrouter`) or `vendor: null` when the provider
  is unknown. Retention returns the identical static object (`is`), and a non-retained selection
  builds the adaptive result. The existing flag-off, error and timeout tests stay green. [S]
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.2, agent-archetypes.4, agent-archetypes.5
  **Design decisions**: D2, D6
  **Dependencies**: 4.2
- [ ] 5.2 Forward the incumbent in `resolve_phase_model` (`model_routing/api.py`) and
  `resolve_archetype_for_phase` (`agents_config.py`), and return the static object on retention. [S]
  **Dependencies**: 5.1
- [ ] 5.3 Write an end-to-end "empty evidence changes no phase" test: an in-process service with a
  catalog that has no priors, and every phase in the phase mapping resolved with `ROUTING_ADAPTIVE=on`
  and compared with static. [S]
  **Spec scenarios**: agent-archetypes.6, model-routing.1
  **Dependencies**: 5.2
- [ ] Checkpoint: run the full coordinator suite (`pytest -m "not e2e and not integration"`), `mypy --strict src/`, and `ruff check .`.

## 6. Documentation

- [ ] 6.1 Document `ROUTING_INCUMBENT_MARGIN` and the retention reason vocabulary in the
  environment-variable section of `agent-coordinator/CLAUDE.md`. [XS]
  **Dependencies**: 5.3
