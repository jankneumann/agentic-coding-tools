# Extend capability-gap tag schema with instruction, polarity, class, and domain prefixes

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `extend-capability-gap-tag-schema-with-evidence-prefixes`
> Effort: S
> Priority: 3

## Summary

Add instruction:AG-nnn, polarity:positive|negative, class:harm|non-compliance|irrelevant, and domain:project|orchestration tag prefixes to the D4 tag schema, document them in docs/guides/memory-conventions.md, and update the session-log emitter and the collect-transcripts writer to emit them.

## Dependencies

- `ri-01`
- `ri-09`

## Acceptance Outcomes

- docs/guides/memory-conventions.md documents the four prefixes with allowed values and an example entry carrying all four.
- A memory entry written by collect-transcripts with --enable carries instruction:, polarity:, class:, and domain: tags when the finding is anchored to an instruction, and a test asserts the tag set.
- Queries by prefix (from ri-05) return entries filtered by polarity:negative and class:harm.

## Rationale

Adopt item 3 in section 4 and section 3.1. The current failure_type enum cannot express harm versus non-compliance and records only what was missing, never that an existing instruction helped or hurt. Positive evidence and harm class are what the remove action floor and the relevance metric are computed from.
