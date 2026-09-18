# Replace the gen-eval semantic judge with a calibrated Noul

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `replace-the-gen-eval-semantic-judge-with-a-calibrated-noul`
> Effort: M
> Priority: 1

## Summary

Rewrite gen_eval.semantic_judge.evaluate_semantic to call
`system_one_decisions.decide(state={criteria, actual_output}, questions={"satisfies": Noul(...)}, site="gen_eval.semantic_judge")`,
gate pass/fail on the returned noul against the existing `min_confidence`
threshold, preserve the module's existing skip result when `decide()`
returns `None` or `system_one_decisions` isn't installed, and call the
existing LLM backend prompt only on failures that need a human-readable
reasoning string.

## Dependencies

- `ri-03`

## Non-Goals

- Measuring Cohen's kappa against a human-labelled set. The
  `calibrate-llm-judge-against-human-labels` change this item originally
  planned to draw a 40-item labelled set from is an unimplemented scaffold
  belonging to a different roadmap (`skill-rightsizing`), itself blocked on
  that roadmap's own `ri-05` — no such dataset exists yet. Kappa validation
  is deferred to a follow-up once a real labelled or mined benchmark corpus
  exists (user decision, recorded in the roadmap's refinement history).
- Wiring `decide()`'s optional `event_sink` telemetry parameter. No
  Langfuse/telemetry convention exists yet for gen-eval; adding one is out
  of scope for this item.

## Acceptance Outcomes

- evaluate_semantic calls system_one_decisions.decide() with one Noul question over
  state={criteria, actual_output} and site="gen_eval.semantic_judge"; Cohen's-kappa
  measurement against a human-labelled set is deferred, not an acceptance bar for
  this item.
- min_confidence gates on the returned noul value with no signature change to
  evaluate_semantic; its test suite is adapted using
  system_one_decisions.testing.stub_decide to stub decide()'s return value for the
  pass/fail path (replacing the old backend-JSON-driven mocks), and continues to
  cover a high-confidence pass, a below-threshold fail, and an unavailable-backend skip.
- When decide() returns None -- whether from one of its own unavailability branches,
  or because system_one_decisions is not installed at all -- evaluate_semantic returns
  its existing skip result, covered by a test for each path.
- Reasoning prose is produced by the existing LLM backend prompt only for items whose
  noul confidence fails the min_confidence threshold, asserted by a test counting
  backend.run() invocations on an all-pass batch (zero).

## Rationale

Pilot step 1: the smallest surface in the proposal, already carrying skip semantics
when the backend is unavailable. The kappa-calibration bar originally planned for
this item is deferred (see Non-Goals) since the human-labelled set it depends on
does not yet exist; a mined-benchmark follow-up is the intended real replacement.
