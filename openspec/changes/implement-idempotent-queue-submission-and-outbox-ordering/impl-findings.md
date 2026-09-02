# Implementation Findings

## Implementation Iteration 1

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | bug | critical | Normal `run_loop` transitions persisted with `save_state` directly, so an injected queue projection callback ran on resume only and never projected live transitions. | Added a RED transition-ordering test and routed normal transition persistence through `persist_and_project(..., mode="submit")`; the callback observes the updated state only after the durable write. |
| 2 | security | high | `WorkQueueService.reconcile_projection` bypassed the required `submit_work` policy check, allowing direct MCP and CLI reconciliation to reach the database without the transport-neutral authorization mapping. | Added a denying-policy RED test and enforced `submit_work` with `context.mode="reconcile"` before the RPC. |
| 3 | edge-case | medium | Bridge projection validation raised `ValueError`, contradicting the documented no-raise helper envelope. | Added RED invalid/reserved-key cases and now return `{status: failed, reason: invalid_projection_key|reserved_projection_key}` before transport. |
| 4 | compatibility | medium | An unkeyed submission could embed reserved projection identity in `input_data` and trigger keyed SQL semantics without the explicit `projection_key` contract. | Added a RED no-database-mutation test and reject reserved identity fields for keyed and unkeyed service submissions. |
| 5 | compatibility | medium | CLI projection failures emitted null success-only fields (`task_id`, `created`, `deduplicated`, `status`) instead of the discriminated failure envelope. | Added exact-envelope RED coverage and emit only `success=false` plus `reason` on submit/reconcile failure. |

All five findings are fixed. No findings at or above the medium remediation threshold remain from the local review.

## Verification

- Coordinator affected suite: 133 passed, 16 skipped. The 16 skips are the explicit real-PostgreSQL degradation because no PostgreSQL runtime is available.
- Skills affected suites: 460 passed.
- Ruff changed-file lint: passed.
- Strict OpenSpec validation: passed.
- OpenAPI validation: passed.
- The combined skills-venv plus coordinator-MCP command is environment-invalid because the skills venv lacks `respx`; the MCP module passed under the coordinator venv.

## Vendor Review Evidence

The canonical read-only dispatcher attempted Antigravity with a 90-second per-vendor bound. It exceeded the parent hard cap and was interrupted; no findings artifact was produced, so vendor quorum is unavailable. No redispatch was attempted. This is degraded optional evidence, not a substitute for the green local gates above.
