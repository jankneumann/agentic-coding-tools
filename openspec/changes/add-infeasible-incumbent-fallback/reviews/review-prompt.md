Review the OpenSpec plan artifacts in openspec/changes/add-infeasible-incumbent-fallback/.
Read proposal.md, design.md (D1-D8), tasks.md, work-packages.yaml, plan-findings.md, contracts/README.md,
and all spec deltas under specs/*/spec.md. Verify concrete claims against the code they name
(agent-coordinator/src/model_routing/, agent-coordinator/src/agents_config.py,
skills/autopilot/scripts/phase_agent.py, skills/autopilot/scripts/smoke_provider_dispatch.py,
skills/coordination-bridge/scripts/routing_fallback.py).
Output ONLY valid JSON conforming to review-findings.schema.json.
Focus on: specification completeness, contract consistency (v1.4 overlay vs spec deltas vs design),
architecture alignment (dispatch honoring the routed provider; allowlisted configured fallback;
local trust boundary), security, and work package validity (scope, locks, the wp-router hold).
Do not re-raise items plan-findings.md records as deferred or out of scope.
