# Change Context: add-live-vendor-capability-and-cost-registry

Canonical traceability for dispatch-governance item dg-01, stacked on finalized dg-00.

## Requirement Traceability Matrix

| Req | Requirement | Contract | Design | Planned tests | Planned implementation | Status |
|---|---|---|---|---|---|---|
| vendor-registry.1 | Typed configured lane registry and filters | `contracts/openapi/v1.yaml#/components/schemas/VendorLane` | D1-D2 | `test_agent_endpoints.py`, `test_vendor_registry.py` | `agents_config.py`, `vendor_registry.py` | implemented |
| vendor-registry.2 | Catalog-owned prices and local health | `CatalogModelPrice`, no-price SQL invariant | D3, D8 | `test_vendor_registry.py`, contract parity | `vendor_registry.py` | implemented |
| vendor-registry.3 | Fresh probes with first-run persistence | `vendor_probe_state`, availability event | D4 | `test_watchdog.py`, `test_watchdog_vendor.py` | `watchdog.py`, `vendor_health.py` | implemented |
| vendor-registry.4 | Bounded, authorized, observable limits | POST contract, `vendor_rate_limits` | D5-D6, D10 | `test_vendor_registry_api.py`, `test_vendor_registry.py` | `coordination_api.py`, `vendor_registry.py` | implemented |
| vendor-registry.5 | Native bridge and exact dispatcher attribution | POST contract | D6-D7 | bridge, review-dispatch, provider-dispatch tests | bridge and dispatcher collectors | implemented |
| vendor-registry.6 | Lane-aware capability/location policy | GET filters | D8-D9 | roadmap policy/orchestrator tests | `orchestrator.py`, `policy.py` | implemented |

## Dependency Boundary

- dg-00 owns model catalog rows, model availability, pricing, and the single routing resolver.
- dg-01 owns configured lane identity/location plus transient probe/rate-limit state.
- dg-04 consumes dg-01's explicit location and capabilities and extends dg-00 selection dimensions.

## Review Remediation

Plan revision 2 incorporates the first panel's repeated findings: exact lane attribution, explicit
identity namespaces and catalog joins, typed location, bounded freshness/reset semantics,
principal-bound writes, deployed health probing, local catalog gating, native bridge behavior,
complete dispatcher ownership, deterministic quote units, fail-closed defaults, audit/retention,
and executable package gates.

## Coverage Summary

- Canonical requirements: 6 implemented, 0 deferred.
- Contract invariant: runtime-state tables contain no price columns.
- Final implementation review converged at semantic quorum 2/2 with 0 blocking and 0 disagreement findings.
