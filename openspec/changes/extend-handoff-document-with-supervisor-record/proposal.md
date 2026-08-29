# Extend handoff document with supervisor record

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `extend-handoff-document-with-supervisor-record`
> Effort: M
> Priority: 1

## Summary

Extend `HandoffDocument` in `agent-coordinator/src/handoffs.py` with a supervisor-scoped record covering active changes and their phases, pending gates with deadlines, standing decisions, and back-edge digest state, so the existing SessionStart hook rehydrates a fresh session into the supervisor role.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- Killing the supervisor session mid-roadmap and starting a fresh one loses no state; the new session lists active changes, pending gates, and next actions from the handoff alone.
- The supervisor record round-trips through serialization with all four sections (active changes, pending gates, standing decisions, back-edge digest state) intact, covered by unit tests.
- The SessionStart hook loads the supervisor record without changes beyond the schema extension.

## Rationale

Makes the supervisor a rehydratable role rather than a resident process (Nondeterministic Idempotence); any fresh session that loads the handoff becomes the supervisor with no other context.
