# Tasks: Extend routing to vendor × location × isolation × dispatch mode

> Change ID: `implement-the-task-router-vendor-x-location-x-model`
> Roadmap item: `dispatch-governance:dg-04`

## 1. Contracts and policy

- [x] 1.1 Add failing static schema tests for the additive HTTP/MCP request and response;
  defer runtime model parity assertions until the policy/transport models exist.
- [x] 1.2 Define typed task profile, lane assignment, exclusion, and provenance schemas.
- [x] 1.3 Define and validate versioned `routing.yaml`; package it in the coordinator image.
- [x] 1.4 Prove no `POST /route/task` route or second resolver is introduced.
- [x] 1.5 Pin bounded persistence projection, typed exclusions, and exact local-fallback
  invariants in contracts; add a schema probe rejecting arbitrary/oversized roadmap path
  lists and unknown nested fields.

  Verified via `tests/model_routing/test_task_routing_contracts.py`,
  `test_routing_policy.py`, `test_routing_policy_config.py`, and
  `test_contracts_generated.py` (all passing); `routing.yaml`'s Dockerfile
  `COPY` line is present per the config-file contract in
  `agent-coordinator/CLAUDE.md`. `grep -rn "route/task" src/` returns no
  matches.

## 2. Feasibility and exact association

- [x] 2.1 Add failing tests for exact lane-to-catalog model association and ambiguity rejection.
- [x] 2.2 Add failing tests for availability, model limit, archetype, location, isolation,
  dispatch-mode, and roadmap-policy exclusions.
- [x] 2.3 Add failing tests proving feasibility runs before dg-00 utility scoring.
- [x] 2.4 Preserve lane identity through candidate ranking and alternatives.
- [x] 2.5 Fail closed on registry errors and report catalog rows without an exact lane.
- [x] 2.6 Materialize explicit configured lane/catalog identities without overwriting live
  catalog data; prove the real roster yields at least one exact routable projection.

  Verified in `src/model_routing/resolver.py` (`build_feasible_assignments`,
  `_lane_exclusion_reason`) and `configured_catalog.py`
  (`ConfiguredCatalogSync`), exercised by `tests/model_routing/test_resolver.py`
  and `test_configured_catalog.py` (all passing).

## 3. Service, API, and audit

- [x] 3.1 Extend `RoutingService` to consume `VendorRegistryService` in process.
- [x] 3.2 Return non-null additive assignment/provenance through HTTP and MCP, prove
  runtime parity with the static contract, and assert
  `response.assignment == response.selected.assignment`.
- [x] 3.3 Add migration 042 and an awaited RPC that atomically persists the sanitized
  routing decision and link-only coordinator audit event.
- [x] 3.4 Preserve exploration, spend, catalog staleness, and dg-00 response compatibility.
- [x] 3.5 Map atomic-durability failure to HTTP 503 and the existing MCP 503 envelope.

  Verified via `src/model_routing/api.py` (`RoutingService.select_model`),
  `database/migrations/042_atomic_routing_audit.sql`, and
  `catalog.py::record_decision_and_audit`; exercised by
  `tests/model_routing/test_service.py`, `test_api.py`, and
  `test_routing_audit.py` (all passing). `CandidateResponse.assignment` and
  `SelectModelResponse.assignment`/`.provenance` were corrected from required
  to `Optional` in this change, matching `select_model()`'s own conditional
  population under `_assignment_enabled` and the dg-00 response shape.

## 4. Local fallback and bridge

- [x] 4.1 Add failing tests for exact provider/model lane selection, rule/default parity,
  configured dispatch-mode fallback order, deterministic agent-ID tie-break, missing-lane
  failure, and no embedded roster.
- [x] 4.2 Add failing tests for explicit fallback source, null catalog key, policy
  provenance, `persisted=false`, and `durable_audit=false`.
- [x] 4.3 Add bridge/MCP proxy support without changing existing static delegation semantics.
- [x] 4.4 Re-run byte-for-byte dg-00 fallback equality tests.

  Implemented as `skills/coordination-bridge/scripts/routing_fallback.py`
  (`local_static_route`, `LocalRoutingFallbackError`) plus
  `coordination_bridge.try_select_model_for_task`, which tries
  `POST /routing/select_model` first and falls back to the local helper only
  when the caller supplies its own already-resolved static provider/model —
  see design D8. `try_resolve_archetype_for_phase`'s own static-fallback path
  is untouched (4.4): `skills/tests/autopilot/test_state_only_archetype_resolver.py`
  and `skills/tests/coordination-bridge/test_archetype_resolve.py` still pass
  unmodified.

## 5. Review, validation, and evidence

- [ ] 5.1 Run focused routing, registry, configured-catalog, API, MCP, bridge, contract,
  Docker, and live PostgreSQL atomicity tests.
- [ ] 5.2 Run full coordinator and affected skills regressions, Ruff, mypy, strict OpenSpec,
  and package DAG/scope gates.
- [ ] 5.3 Send the exact diff and validation evidence to every configured vendor-panel harness.
- [ ] 5.4 Resolve confirmed blocking findings and repeat panel review to semantic quorum.
- [ ] 5.5 Update traceability, session log, validation report, and PhaseRecord.
- [ ] 5.6 Push the feature branch and open a stacked PR against
  `openspec/add-live-vendor-capability-and-cost-registry`.
- [ ] 5.7 Reconcile roadmap/checkpoint only after validation and CI are green.
