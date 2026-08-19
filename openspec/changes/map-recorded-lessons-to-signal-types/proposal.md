# Map recorded lessons to signal types

> Parent roadmap: `closed-loop-learning`
> Change ID: `map-recorded-lessons-to-signal-types`
> Effort: S
> Priority: 1

## Summary

Extend the existing remember tool path so failure lessons are mapped to one or more registry signal types alongside their capability_gap and affected_skill tags, with recorded strength usable by the recall economics.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A lesson recorded via the remember tool persists with at least one signal-type mapping alongside its memory-conventions tags, stored in coordinator Postgres.
- Lessons mapped to a given signal type are queryable through the coordinator from any machine reaching it.
- Writes use the memory-conventions tag schema unchanged except for the signal-type extension.

## Rationale

Recall by meaning requires lessons to be indexed by signal type at write time; this wires the writer half so the detection hook has something to recall, satisfying the writer-plus-automated-reader rule for the new state.
