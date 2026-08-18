# Calibrate the LLM judge against human labels

> Parent roadmap: `skill-rightsizing`
> Change ID: `calibrate-llm-judge-against-human-labels`
> Effort: M
> Priority: 3

## Summary

Human-label 40 stratified replay outputs, measure agreement between those labels and the LLM judge with Cohen's kappa, and publish the judge's error rate with every subsequent result that uses it.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Cohen's kappa is reported per judged dimension against the 40-item labelled set.
- Dimensions scoring below kappa 0.7 are excluded from the scorecard.
- The judge runs blind to arm identity and with randomized presentation order.
- The judge does not receive the skill under test in its context.

## Rationale

Where LLM judgment is unavoidable, calibration converts "the model grades itself" into "the model grades itself and we know how often it is wrong" — a defensible position rather than a fatal one.
