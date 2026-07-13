# Make the orchestrator obey the router

> Parent roadmap: `repo-improvement`
> Change ID: `make-the-orchestrator-obey-the-router`
> Effort: M
> Priority: 1

## Summary

Call route/task before each dispatch_fn and pass the decision into the dispatch context as a contract, execute switch decisions with ledger-verified re-dispatch to the alternate vendor, add a global iteration cap and no-progress detector to the roadmap loop, un-stub _estimate_cost_delta/_estimate_wait_seconds against the registry, and turn the silent apply_phase_outcome no-op on a missing state file into an error.

## Dependencies

- `ri-03`
- `ri-05`

## Acceptance Outcomes

- An induced rate-limit on the preferred vendor causes an observed, ledger-verified dispatch to the alternate vendor.
- Cost and latency deltas are persisted in checkpoint.json as the roadmap-orchestration spec specifies.
- A stuck dispatch_fn trips the global iteration cap or no-progress detector instead of spinning indefinitely.

## Rationale

The policy engine currently only logs vendor-switch decisions and nothing executes them; closing this decide-but-don't-act gap is what makes routing decisions real and enables the switch_if_time_saved policy — which this roadmap can opt into once a cost_ceiling_usd is set (it currently uses the safe wait default).
