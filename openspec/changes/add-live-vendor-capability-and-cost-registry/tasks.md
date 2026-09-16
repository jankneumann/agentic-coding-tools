# Tasks: Add live vendor capability and availability registry

> Change ID: `add-live-vendor-capability-and-cost-registry`
> Roadmap item: `dispatch-governance:dg-01`

## 1. Contracts and configured identity

- [x] 1.1 Add failing parity tests for OpenAPI, events, SQL, and runtime models.
- [x] 1.2 Define lane, provider, policy, and catalog identities without heuristic joins.
- [x] 1.3 Add failing `AgentEntry` tests for typed location and identity fields.
- [x] 1.4 Declare location, policy vendor, and catalog vendor explicitly in bundled agents.yaml.
- [x] 1.5 Define additive probe and rate-limit tables with no pricing columns.

## 2. Registry core

- [x] 2.1 Add failing tests for lane aggregation and conjunctive eligibility filters.
- [x] 2.2 Add failing tests for first/current/stale/no-method probes and exact expiry boundaries.
- [x] 2.3 Add failing concurrent RPC tests for bounded reset, replay conflict, and compaction; fail when Postgres-required tests skip.
- [x] 2.4 Add failing tests for endpoint-kind local gating, model-scoped limits, and exact projections.
- [x] 2.5 Add failing tests for request quotes, catalog misses, batching, and no duplicate prices.
- [x] 2.6 Implement migration and registry service with injected UTC time.
- [x] 2.7 Add structured audit/log records for lifecycle and degraded-path decisions.

## 3. Authenticated API and watchdog

- [x] 3.1 Add failing API tests for filters, three auth methods, report operation, 403, coded 404, 409, and typed 202.
- [x] 3.2 Implement both GET routes and authenticated rate-limit ingestion.
- [x] 3.3 Add failing watchdog tests for first-poll persistence without transitions.
- [x] 3.4 Add failing watchdog tests proving per-lane write failures do not suppress events.
- [x] 3.5 Persist every vendor-health snapshot with the specified TTL.
- [x] 3.6 Package and resolve the probe/roster in the image and start watchdog without notifier dependency.
- [x] 3.7 Schedule bounded rate-limit compaction through watchdog.

## 4. Bridge and exact dispatcher reporting

- [x] 4.1 Add failing bridge tests for repository-native results, auth, errors, and payload validation.
- [x] 4.2 Implement registry read/write helpers using existing bridge conventions.
- [x] 4.3 Add failing result-collector tests for ReviewResult/phase payload agent ID, per-attempt capacity, and reset metadata.
- [x] 4.4 Report review-dispatch and provider-dispatch capacity failures once per result.
- [x] 4.5 Preserve dispatch outcomes when observation reporting fails.
- [x] 4.6 Audit and skip ambiguous legacy provider-only observations.

## 5. Roadmap policy

- [x] 5.1 Add failing tests for capability/archetype/mode/location filters and lane exclusion.
- [x] 5.2 Add failing tests for namespace normalization and lane provenance.
- [x] 5.3 Add failing tests for request-scoped decimal quotes and unknown cost behavior.
- [x] 5.4 Add failing tests for fail-closed default, coded bridge failures, and explicit YAML fallback.
- [x] 5.5 Add failing tests for provider-scoped legacy exclusion and unknown cost-guard provenance.
- [x] 5.6 Inject bridge-backed registry provider and remove the hardcoded vendor roster.
- [x] 5.7 Ensure static tiers cannot populate USD deltas or enforce USD ceilings.

## 6. Review, validation, and evidence

- [x] 6.1 Run focused coordinator, watchdog, bridge, dispatcher, policy, and orchestrator suites.
- [x] 6.2 Run full coordinator and skills regressions, Ruff, mypy, migration, contract, DAG, and strict OpenSpec gates.
- [x] 6.3 Send diff and exact validation evidence to every configured vendor-panel harness.
- [x] 6.4 Resolve confirmed blocking findings and record consensus.
- [x] 6.5 Update traceability, session log, validation report, and PhaseRecord.
- [x] 6.6 Reconcile roadmap/checkpoint only after every validation gate passes.
- [x] 6.7 Push commits and open a stacked PR against `openspec/add-adaptive-model-router`.
