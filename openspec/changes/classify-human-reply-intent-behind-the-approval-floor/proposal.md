# Classify human reply intent behind the approval floor

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `classify-human-reply-intent-behind-the-approval-floor`
> Effort: M
> Priority: 6

## Summary

Replace relay.parse_reply's first-word keyword match with Choice({approve, deny, resolved, skip, guidance}) over the reply text, keeping the sender allowlist, requiring distribution["approve"] >= 0.97 for an approval and mapping everything else to guidance.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- Replies from senders outside the allowlist are rejected before any decision call, asserted by a call-count test.
- approve is returned only when distribution["approve"] >= 0.97; every other case, including a degraded decision, returns guidance, covered by a parametrised test around 0.97.
- A corpus of recorded replies shows no reply currently classified non-approve becoming approve without meeting the floor.
- The change carries a security review recording the trust-model impact, and every classified reply logs its distribution alongside the sender.

## Rationale

Pilot step 7 and the proposal's explicit security item. "Looks good, go ahead" falling to guidance is real brittleness, but this is a human authorization channel, so widening what counts as approved changes the trust model. It ships last, after live calibration has been demonstrated at the promoted sites, and as a security review rather than a quick win.
