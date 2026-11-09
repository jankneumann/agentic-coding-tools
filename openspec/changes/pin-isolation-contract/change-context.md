# Change Context: pin-isolation-contract

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| vendor-dispatch.1 | `specs/vendor-dispatch/spec.md` | Producer and consumer derive the accepted isolation vocabulary from one canonical definition, with published schema parity and explicit rejection of unknown values. | --- | D1, D4 | `agent-coordinator/src/isolation_contract.py`; `agent-coordinator/src/agents_config.py`; `agent-coordinator/src/model_routing/api.py`; `agent-coordinator/src/model_routing/routing_policy.py`; `skills/coordination-bridge/scripts/routing_fallback.py` | `agent-coordinator/tests/test_isolation_contract.py`; `agent-coordinator/tests/model_routing/test_task_routing_contracts.py`; `agent-coordinator/tests/model_routing/test_routing_policy.py` | pass `2d240bf1` |
| vendor-dispatch.2 | `specs/vendor-dispatch/spec.md` | Resolution follows router, agents.yaml, then none; absence falls through, invalid presence fails, and the selected source is recorded. | --- | D2 | `agent-coordinator/src/isolation_contract.py`; `agent-coordinator/src/agents_config.py`; `agent-coordinator/src/model_routing/resolver.py`; `skills/coordination-bridge/scripts/routing_fallback.py` | `agent-coordinator/tests/test_isolation_contract.py`; `agent-coordinator/tests/model_routing/test_resolver.py` | pass `2d240bf1` |
| vendor-dispatch.3 | `specs/vendor-dispatch/spec.md` | Isolation resolves for an exact agent and dispatch-mode pair, including per-mode overrides and router/local-fallback parity. | --- | D2, D3 | `agent-coordinator/src/agents_config.py`; `agent-coordinator/src/vendor_registry.py`; `agent-coordinator/src/model_routing/resolver.py`; `skills/coordination-bridge/scripts/routing_fallback.py`; `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `agent-coordinator/tests/test_agents_config_isolation.py`; `agent-coordinator/tests/test_vendor_registry.py`; `agent-coordinator/tests/model_routing/test_resolver.py`; `skills/tests/coordination-bridge/test_routing_fallback.py`; `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py` | pass `2d240bf1` |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | One stdlib-only module prevents runtime vocabulary drift while remaining loadable during coordinator outages. | `agent-coordinator/src/isolation_contract.py`, imported normally by coordinator code and through the fallback checkout-root shim. | One executable definition serves both producer and outage consumer paths. |
| D2 | Absence and invalid presence have different safety semantics, and provenance must remain observable. | Typed validation and `IsolationResolution(value, source)` plus mode-aware exact-agent lookup. | Fails closed on bad data without turning a missing optional value into an error. |
| D3 | Dispatch mode is known before assignment emission and can change the required posture. | Mode overrides in `ModeConfig`, registry projection, resolver, local fallback, and dispatcher parsing. | Keeps reachable and outage routing consistent for the same agent/mode. |
| D4 | Adding a new posture changes a cross-boundary security contract. | Canonical values remain exactly `none`, `worktree`, and `sandbox`; parity tests reject drift. | `container` requires a later reviewed amendment rather than accidental widening. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| plan-preapproval | wp-isolation-contract | multi-vendor plan review | blocking/high | fix | Approved design and test matrix incorporate canonical vocabulary, mode-aware configuration, exact identity, serialization, fallback parity, and invalid-value cases. |

## Coverage Summary

- **Requirements traced**: 3/3
- **Tests mapped**: 3 requirements have at least one planned test
- **Evidence collected**: 3/3 requirements have pass evidence
- **Gaps identified**: Full coordinator coverage passes as a two-process partition (2650 + 193); one-process execution exposes pre-existing policy-test global-state contamination
- **Deferred items**: `container` vocabulary amendment; dg-06 execution wiring; dg-07 sandbox enforcement
