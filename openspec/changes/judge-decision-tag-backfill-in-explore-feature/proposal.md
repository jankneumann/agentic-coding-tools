# Judge decision-tag backfill in explore-feature

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-decision-tag-backfill-in-explore-feature`
> Effort: S
> Priority: 4

## Summary

Replace the seven keyword lists in backfill_decision_tags with Choice(capability, the seven capability tags plus "none") over each decision's title and rationale, batched as many questions over one session-log phase as shared state, and feed ChoiceAnswer.probabilities into the existing 0.5/0.8 confidence buckets.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- The report's confidence field is populated from ChoiceAnswer.probabilities and the existing 0.5/0.8 bucketing code is unchanged, asserted by a test over a session-log fixture.
- A decision matching no capability yields the "none" option and is excluded from proposed edits.
- All decisions in one session-log phase are answered in a single batched call, asserted by a call-count test.
- The keyword map remains as the fallback and the script still only proposes edits for agent review; no file is written by the script itself.

## Rationale

Pilot step 4 and the textbook shape for this primitive: routing with a no-match option. The script already emits a confidence the report buckets, but keyword-derived confidence is not calibrated, so the report format needs no change while the number behind it becomes meaningful.
