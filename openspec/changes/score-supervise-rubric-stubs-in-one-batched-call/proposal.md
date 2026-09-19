# Score supervise rubric stubs in one batched call

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `score-supervise-rubric-stubs-in-one-batched-call`
> Effort: M
> Priority: 4

## Summary

Add `skills/supervise/scripts/rubric_score.py`, a new sibling script that scores every
requested candidate-work stub on all 5 rubric factors with up to 100 `Score` questions in
one batched `decide()` call. `skills/supervise/SKILL.md`'s Rank step tries it first;
only when it reports unavailable does the host dispatch the sub-agent analyst archetype,
exactly as before. `supervise-rubric-score.schema.json`'s `justification` becomes optional
(a live `Score` answer has no free-text field to fill it with), and `digest.py`'s
`rank_candidates` substitutes a legend-derived label for a factor's own score when
justification is absent. See `design.md` for the full grounding and nine numbered
decisions (D1-D9), including two scope corrections to this item's own scaffolded acceptance
outcomes (D4, D8).

## Dependencies

- `ri-05`

## Acceptance Outcomes

- The rubric-score contract marks `justification` optional and `rank_candidates` renders a
  Score-legend label in the digest's `justifications` field when it is absent, covered by
  `test_rank_renders_score_legend_when_justification_is_absent` in `test_digest.py`.
- Twenty stubs are scored on five factors in one batched call (100 `Score` questions) and
  the result validates against the updated schema, asserted in
  `test_rubric_score.py::TestScoreBatch::test_twenty_stubs_five_factors_is_one_hundred_questions`.
- Structural-error handling (missing, partial, invalid, late) is exercised by
  `test_rubric_score.py`'s degradation tests (module unavailable, malformed/missing
  per-factor answers -- all-or-nothing per design D3) and by
  `test_batched_rubric_scorer_is_tried_before_the_analyst_archetype_fallback`, which asserts
  `SKILL.md` tries the batched scorer first and dispatches the sub-agent analyst archetype
  only on its failure -- the fallback framing the original acceptance outcome asked for.
- **Scope-corrected (design D8)**: no recorded manifest or archived analyst output exists
  anywhere in this codebase to measure a real agreement rate from. This item ships
  `compute_agreement()`, the report function itself, with unit tests against an explicitly
  synthetic fixture pair -- it does not claim a real production agreement rate, mirroring
  `ri-06`'s pattern of building the harness before real shadow data exists.

## Rationale

Pilot step 5. The current prompt runs under a 120-second timeout with one retry and rejects
"missing, partial, invalid, or late output" — a description of the failure mode this
primitive removes. The schema decision must land with the change because
`rubric-score.schema.json` marks `justification` required per factor; the digest is
deterministic by design, so this is a contract change rather than an architecture change.
