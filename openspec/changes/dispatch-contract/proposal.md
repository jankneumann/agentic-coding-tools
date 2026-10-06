# Publish the supervisor-worker dispatch contract

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `dispatch-contract`
> Effort: L
> Priority: 1

## Summary

Publish versioned dispatch-request and dispatch-result JSON schemas as the single definition of the supervisor-worker boundary; emit results from loop-state via runner.py emit-result; add gate provenance with posture-digest re-evaluation, execution_profile, review_requirements, degradations[], and the parked kinds permission_blocked and capability_unavailable, with a closure contract test so every schema-permitted parked shape has a supervisor answer path.

## Dependencies

- None

## Acceptance Outcomes

- dispatch-request and dispatch-result schemas exist under openspec/schemas and execution.py and orchestrator.py validate against them with existing fixtures passing.
- runner.py emit-result produces a schema-valid result for every terminal and parked loop-state shape, verified end to end.
- A closure contract test fails when any schema-permitted parked kind/gate combination lacks a supervisor answer or resume path.
- A posture-derived gate block clears on resume after a posture change while a human rejection does not.
- execution_profile, review_requirements, and degradations[] are carried end to end, and permission_blocked and capability_unavailable parks are routed to the operator as single escalations.

## Rationale

Every stall in the first supervised run occurred at an unwritten part of the supervisor-worker boundary; queue-dispatched work (team-work-queue, owner-routed-escalation, queue-dispatch-owner-acceptance) is built on it.
