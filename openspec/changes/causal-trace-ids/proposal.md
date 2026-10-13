# Add on-behalf-of chains and causal trace IDs to coordinator records

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `causal-trace-ids`
> Effort: L
> Priority: 2

## Summary

Add on_behalf_of principal chains and correlation_id / causation_id fields to coordinator audit entries, events, approvals, handoffs, and PhaseRecord.write_both() output, with a causal-chain query and loop guards for echo events.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- Given any audit entry, a query returns its full causal chain back to the originating event or human request.
- Every audit entry, event, approval, handoff, and phase record written after the change carries a non-empty on_behalf_of chain ending in a human principal.
- Events caused by an agent's own action are identifiable as echoes by causation ID, and a loop guard rejects causal chains exceeding the configured hop count.
- In solo mode the chain resolves to the sole repository principal and no new prompts appear.

## Rationale

P1 and P9 require every action to be traceable to a human principal and its trigger; causal IDs are what later lets corrections be linked to the trace that produced them and lets agents ignore echoes of their own actions.
