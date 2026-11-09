# Add signal_assertions to gen-eval regression scenarios

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-signal-assertions-to-gen-eval-regression-scenarios`
> Effort: M
> Priority: 5

## Summary

Extend the gen-eval scenario schema with a signal_assertions block that names a signal, its expected value or relation against a control, and its source layer, and make the runner enforce it. Upgrade existing converted failure-record regression scenarios to assert the signal that identified the original bug.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- The gen-eval scenario schema accepts signal_assertions, and the runner fails a scenario whose signal deviates even when its outcome assertion passes.
- At least three existing converted regression scenarios are upgraded with signal assertions and pass.

## Rationale

Regression scenarios that only check outcomes can pass while the bug's signal regresses. Asserting the identifying signal extends the failure-record-to-regression work using the shared snapshot format.
