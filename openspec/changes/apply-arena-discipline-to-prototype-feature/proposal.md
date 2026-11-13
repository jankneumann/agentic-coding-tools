# Apply arena discipline to prototype-feature

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `apply-arena-discipline-to-prototype-feature`
> Effort: L
> Priority: 4

## Summary

Stop naming the scoring phases in variant prompts and score a held-out check set after the variants finish. Add an optional cross-family model judge whose recommendation is shown beside the human pick, cap grafting from non-winning variants to one or two named parts, and emit a reframe finding to iterate-on-plan when variants diverge past a threshold.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- The variant prompt no longer names the scoring phases, and a held-out check set the variants never saw is scored after they finish.
- When enabled, the judge's model family, resolved from archetypes.yaml tiers, differs from every variant's, and its recommendation is recorded beside the human pick in prototype-findings.md; the pick itself stays human.
- Grafting from non-winning variants is limited to at most two named parts, and the limit is enforced in the convergence step.
- Divergence past the threshold emits a reframe finding that /iterate-on-plan --prototype-context consumes.

## Rationale

Phase 3: variants currently see exactly how they will be scored, which invites rubric-fitting. The judge should reuse the cross-family independence rule set up in ri-08 instead of defining a second one, and the human pick must stay a human gate.
