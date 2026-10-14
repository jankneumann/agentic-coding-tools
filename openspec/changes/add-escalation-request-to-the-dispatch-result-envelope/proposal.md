# Add escalation_request to the dispatch-result envelope

> Parent roadmap: `operator-front-door`
> Change ID: `add-escalation-request-to-the-dispatch-result-envelope`
> Effort: S
> Priority: 2

## Summary

Extend the dispatch-result summary envelope from multiplayer-collaboration ri-21 with an optional escalation_request field carrying a target (model tier, vendor, or human), a reason, and evidence refs.

## Dependencies

- None

## Acceptance Outcomes

- The dispatch-result schema accepts an escalation_request with a target tier or vendor or human, a reason, and evidence refs.
- Schema tests reject escalation requests that lack a reason, name an unknown target, or carry malformed evidence refs.
- Existing dispatch results without escalation_request still validate, so ri-21 producers need no change.

## Rationale

Gives workers a structured way to ask for more capability instead of failing or silently looping; the escalation ladder and the coordinator queue consume it. Extends the existing ri-21 schema rather than forking it, as the constraints require.
