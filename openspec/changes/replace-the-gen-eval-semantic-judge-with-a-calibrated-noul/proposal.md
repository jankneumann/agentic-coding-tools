# Replace the gen-eval semantic judge with a calibrated Noul

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `replace-the-gen-eval-semantic-judge-with-a-calibrated-noul`
> Effort: M
> Priority: 1

## Summary

Rewrite gen_eval.semantic_judge.evaluate_semantic to ask one Noul("The actual output satisfies the criteria") over {criteria, actual_output}, using noul as the confidence that min_confidence already thresholds, and call the existing LLM prompt only on failures that need a human-readable reasoning string.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- evaluate_semantic scores the 40-item human-labelled set from calibrate-llm-judge-against-human-labels and reaches Cohen's kappa >= 0.7 on the judged dimension; the measured kappa is recorded in the change's artifacts.
- min_confidence gates on noul with no signature change, and existing semantic_judge tests pass unmodified.
- When the decision helper returns None the module still returns its existing skip result, covered by a test.
- Reasoning prose is produced by an LLM only for items that fail the threshold, asserted by a test counting LLM invocations on an all-pass batch (zero).

## Rationale

Pilot step 1: the smallest surface in the proposal, already carrying skip semantics when the backend is unavailable. It is also the site where the active calibrate-llm-judge-against-human-labels change supplies a 40-item human-labelled set, so this item is where the kappa bar is first paid rather than assumed.
