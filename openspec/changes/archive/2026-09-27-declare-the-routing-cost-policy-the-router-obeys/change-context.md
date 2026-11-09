# Change Context

## Requirement Traceability Matrix

| Requirement | Contract Ref | Design Decision | Files Changed | Evidence |
| --- | --- | --- | --- | --- |
| Cost-aware assignment selection | `contracts/config/routing-cost-policy.schema.json` | D1, D2 | `agent-coordinator/routing.yaml`, `agent-coordinator/src/model_routing/routing_policy.py`, `agent-coordinator/src/model_routing/api.py` | `test_routing_cost_policy.py::test_router_uses_first_available_cost_tier` |
| Cost tier provenance | --- | D3 | `agent-coordinator/src/model_routing/api.py` | `test_routing_cost_policy.py::test_router_uses_first_available_cost_tier` |

## Design Decision Trace

- D1: Optional policy section keeps older routing documents valid.
- D2: Feasibility filtering runs before tier preference; utility ranking stays within the selected tier.
- D3: Decision provenance records the selected cost tier.

## Coverage Summary

Both requirements have direct tests; the model-routing suite passes.
