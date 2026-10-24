# Audit decision trails cross-model against the transcript

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `audit-decision-trails-cross-model-against-the-transcript`
> Effort: L
> Priority: 3

## Summary

Extend audit-choices so the auditor is resolved from archetype tiers to a vendor/model family different from the author's, reads the normalized session transcript via collect-transcripts adapters in addition to the diff, spec and session-log, and reports decisions present in one but missing from the other. Evidence cells become resolvable pointers, and the rendered ledger ends with an Attention section.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- An audit whose auditor vendor equals the author vendor is refused, or recorded as a degraded inline-fallback with the reason, and is never silently accepted.
- A validator rejects any ledger entry whose evidence is free text rather than a resolvable transcript event id, commit SHA or file:line pointer.
- Given a fixture transcript containing a decision absent from the session-log, the audit reports it as a missing-from-trail finding.
- The rendered ledger ends with an Attention section naming the reviewer model and listing the entries to read first; the auditor model comes from archetypes.yaml tiers, with no hardcoded model ids, and any decision-choices schema additions are optional.

## Rationale

Phase 3 calibrated judgement: decision trails are audited only against the diff, never against what was said in the session, and by an auditor who may share the author's model family. This should share one independence rule with ri-01's author-identity check and add-eliminative-adversarial-review-mode's same-vendor refusal.
