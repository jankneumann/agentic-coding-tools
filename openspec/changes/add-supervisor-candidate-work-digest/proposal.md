# Add supervisor candidate-work digest

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `add-supervisor-candidate-work-digest`
> Effort: S
> Priority: 3

## Summary

Add the supervisor's periodic digest to the human, ranking pending candidate-work stubs so approved ones can be slotted into the roadmap, with digest state persisted in the supervisor handoff record's back-edge section.

## Dependencies

- `ri-02`
- `ri-05`
- `ri-11`
- `ri-16`

## Acceptance Outcomes

- A supervise session produces a ranked digest of schema-valid candidate stubs on request or at its periodic checkpoint.
- Approving a stub from the digest routes it into /plan-roadmap without leaving the conversation.
- Digest state (last-digested stubs, standing decisions) survives session rehydration via the handoff record.

## Rationale

The digest is the conversational surface of the standardized back-edge — the supervisor, not a human courier, carries discovery findings into roadmap decisions.
