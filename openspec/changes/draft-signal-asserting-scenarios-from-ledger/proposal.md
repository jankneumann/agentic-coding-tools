# Draft signal-asserting scenarios when a debugging ledger closes

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `draft-signal-asserting-scenarios-from-ledger`
> Effort: S
> Priority: 6

## Summary

When a debugging session closes with a validated root cause, have the debugging skill propose a gen-eval regression scenario seeded from the ledger's strongest signal and its control.

## Dependencies

- `ri-03`
- `ri-12`

## Acceptance Outcomes

- Closing a debugging ledger with a validated root cause emits a draft scenario whose signal_assertions reference the ledger's strongest signal.
- The draft scenario validates against the gen-eval scenario schema.
- Closing a ledger without a validated root cause emits no draft scenario.

## Rationale

This closes the loop from investigation to regression coverage, so the evidence that identified a bug becomes a durable check instead of being lost after the fix.
