# Add why mode to explain-code with epistemic tiers

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `add-why-mode-to-explain-code-with-epistemic-tiers`
> Effort: M
> Priority: 4

## Summary

Add a why mode to explain-code, backed by a deterministic why_trace script that joins git blame, commit, PR, change-id and docs/decisions entries via decision_index.py, with every claim tagged Direct / Supported / Inferred / Speculative / Unknown. Add an optional evidence_level field with the same vocabulary to review-findings.schema.json.

## Dependencies

- None

## Acceptance Outcomes

- why_trace returns the blame, commit, change-id and decision chain for a fixture repository, and an explicit empty result when no decision record covers the line.
- The explain-code SKILL documents the tier vocabulary and the null-result and embedded-hypothesis rules; no standalone /why skill is added.
- evidence_level is optional in review-findings.schema.json, appears in the prompt contract derived by review_findings_schema.prompt_contract, and every existing emitter still validates; the schema diff is limited to that one field.

## Rationale

Phase 3: no tool answers 'why is this code like this' from the decision record, and answers do not distinguish quoted evidence from inference. A shared tier vocabulary makes judgements calibrated across explain-code and reviews.
