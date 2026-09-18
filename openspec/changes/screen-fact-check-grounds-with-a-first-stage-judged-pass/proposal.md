# Screen fact-check grounds with a first-stage judged pass

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `screen-fact-check-grounds-with-a-first-stage-judged-pass`
> Effort: L
> Priority: 3

## Summary

Split fact_check.run into two stages: stage one asks one Noul per finding for Ground A ("the code the finding describes is not in the subject file's diff") and one Noul("a line in this diff directly contradicts the finding's central claim") as a Ground-B screen; stage two runs the existing economy-tier LLM prompt only for findings whose Ground-B probability crosses a config-held threshold.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A batch whose findings all screen below the Ground-B threshold makes zero stage-two LLM calls, asserted by a call-count test.
- Ground-B verdicts still require a quoted diff line validated by _evidence_line_in_subject_diff; no finding is refuted on the screen alone, covered by a test.
- Protected-subject vetoes are applied in code before any call, asserted by a fixture where a protected subject is never sent.
- Ground-A refutations from stage one reproduce the existing prompt's labels on a recorded fact-check batch, with the agreement rate recorded.

## Rationale

Pilot step 5. Ground B needs a quoted diff line that the code verifies literally via _evidence_line_in_subject_diff, which this primitive cannot produce, so the two-stage pattern is mandatory rather than optional. Most review batches would never reach stage two, removing a 90-line prompt from the common path.
