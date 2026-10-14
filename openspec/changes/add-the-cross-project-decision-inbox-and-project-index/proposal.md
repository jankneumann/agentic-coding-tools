# Add the cross-project decision inbox and project index

> Parent roadmap: `operator-front-door`
> Change ID: `add-the-cross-project-decision-inbox-and-project-index`
> Effort: L
> Priority: 2

## Summary

Coordinator tables and endpoints for a decision inbox holding cards from every project and roadmap with states open, answered, applied, or expired-to-default and idempotent answers, plus a project index listing each registered repository with its active roadmaps, in-flight items, and open-card count from one call.

## Dependencies

- `ri-02`
- `ri-06`

## Acceptance Outcomes

- A decision card posted by a worker in project A is returned by an inbox query spanning all registered projects.
- Answering the same card twice applies exactly once, proven by a test asserting a single applied transition.
- An unanswered card past its deadline resolves to its declared default and is logged as an expiry, not as a human decision.
- A single coordinator call returns every registered repository with its active roadmaps, in-flight items, and open-card count.

## Rationale

Lets the Supervisor thread answer what needs the operator across everything from one query instead of rehydrating each repo. Builds on the approval-gate service from always-on-agent-automation ri-05 rather than forking it; needs the card schema and reads in-flight items from the dispatch queue.
