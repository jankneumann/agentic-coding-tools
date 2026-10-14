# Add a signed coordinator dispatch queue with leases

> Parent roadmap: `operator-front-door`
> Change ID: `add-a-signed-coordinator-dispatch-queue-with-leases`
> Effort: L
> Priority: 2

## Summary

A postgres-backed dispatch queue in the coordinator holding coordinator-signed dispatch requests that workers claim exactly once, with leases, heartbeats, and requeue on lease expiry, reusing the ri-21 dispatch-request and dispatch-result schemas. The always-on-agent-automation ri-07 tracker adapter becomes one producer into it.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- A concurrency test with two workers claiming simultaneously never hands the same dispatch to both.
- A concurrency test shows a lease that expires without a heartbeat returns the dispatch to the queue and it is claimable again.
- Dispatch requests without a valid coordinator signature are rejected at claim time.
- Queue rows store dispatch requests and results that validate against the unmodified ri-21 schemas, and the ri-07 tracker adapter enqueues through the same API as any other producer.

## Rationale

Phase 2 spine: the launcher, cloud overflow, and project index all need a single claimable source of work. Reuses ri-21 schemas and the ri-07 adapter rather than a parallel dispatch path; ordered after ri-03 because both touch the dispatch-result contract.
