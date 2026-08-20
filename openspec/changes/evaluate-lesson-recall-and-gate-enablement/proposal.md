# Evaluate lesson recall and gate enablement

> Parent roadmap: `closed-loop-learning`
> Change ID: `evaluate-lesson-recall-and-gate-enablement`
> Effort: M
> Priority: 2

## Summary

Add a gen-eval paraphrase-recall scenario asserting cross-session, cross-vendor recall under different surface wording, measure the false-positive injection rate against a configured threshold, and gate default-on enablement on beating the no-injection baseline.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A gen-eval scenario shows a lesson recorded from one failure being injected in a later session (different vendor or machine via the coordinator) when the same root cause recurs under different surface wording that exact string matching would miss.
- The measured false-positive injection rate is below the configured threshold.
- Default-on enablement is recorded only after the scenario beats the no-injection baseline; until then the feature stays off by default.

## Rationale

The semantic-context-injection norm requires any context-injecting mechanism to be eval-gated off by default until it records a pass against baseline; the paraphrase scenario also proves the semantic trigger succeeds where exact string matching would fail.
