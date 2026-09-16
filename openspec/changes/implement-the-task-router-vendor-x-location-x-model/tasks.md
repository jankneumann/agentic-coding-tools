# Tasks: Extend routing to vendor × location × isolation × dispatch mode

> Change ID: `implement-the-task-router-vendor-x-location-x-model`
> Roadmap item: `dispatch-governance:dg-04`

## 1. Contracts and policy

- [ ] 1.1 Add failing static schema tests for the additive HTTP/MCP request and response;
  defer runtime model parity assertions until the policy/transport models exist.
- [ ] 1.2 Define typed task profile, lane assignment, exclusion, and provenance schemas.
- [ ] 1.3 Define and validate versioned `routing.yaml`; package it in the coordinator image.
- [ ] 1.4 Prove no `POST /route/task` route or second resolver is introduced.
- [ ] 1.5 Pin bounded persistence projection, typed exclusions, and exact local-fallback
  invariants in contracts; add a schema probe rejecting arbitrary/oversized roadmap path
  lists and unknown nested fields.

## 2. Feasibility and exact association

- [ ] 2.1 Add failing tests for exact lane-to-catalog model association and ambiguity rejection.
- [ ] 2.2 Add failing tests for availability, model limit, archetype, location, isolation,
  dispatch-mode, and roadmap-policy exclusions.
- [ ] 2.3 Add failing tests proving feasibility runs before dg-00 utility scoring.
- [ ] 2.4 Preserve lane identity through candidate ranking and alternatives.
- [ ] 2.5 Fail closed on registry errors and report catalog rows without an exact lane.
- [ ] 2.6 Materialize explicit configured lane/catalog identities without overwriting live
  catalog data; prove the real roster yields at least one exact routable projection.

## 3. Service, API, and audit

- [ ] 3.1 Extend `RoutingService` to consume `VendorRegistryService` in process.
- [ ] 3.2 Return non-null additive assignment/provenance through HTTP and MCP, prove
  runtime parity with the static contract, and assert
  `response.assignment == response.selected.assignment`.
- [ ] 3.3 Add migration 042 and an awaited RPC that atomically persists the sanitized
  routing decision and link-only coordinator audit event.
- [ ] 3.4 Preserve exploration, spend, catalog staleness, and dg-00 response compatibility.
- [ ] 3.5 Map atomic-durability failure to HTTP 503 and the existing MCP 503 envelope.

## 4. Local fallback and bridge

- [ ] 4.1 Add failing tests for exact provider/model lane selection, rule/default parity,
  configured dispatch-mode fallback order, deterministic agent-ID tie-break, missing-lane
  failure, and no embedded roster.
- [ ] 4.2 Add failing tests for explicit fallback source, null catalog key, policy
  provenance, `persisted=false`, and `durable_audit=false`.
- [ ] 4.3 Add bridge/MCP proxy support without changing existing static delegation semantics.
- [ ] 4.4 Re-run byte-for-byte dg-00 fallback equality tests.

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
