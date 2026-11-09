# Capture human interventions as labeled corrections

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `intervention-capture`
> Effort: M
> Priority: 4

## Summary

Record human edits to agent output, overrides, rejections, reverts of autonomous actions, and unnecessary or missed escalations as correction records linked by causal ID to the producing trace, classified intent-level or execution-level, and feed them into the closed-loop-learning flywheel.

## Dependencies

- `ri-04`
- `ri-09`

## Acceptance Outcomes

- A reverted or human-edited agent commit produces a correction record linked to its trace and classified intent vs execution.
- Correction records are written into the closed-loop-learning store, and no new learning store is created.
- Only artifacts in the shared repository and coordinator are captured; private session transcripts are excluded unless the principal opts in.

## Rationale

Every human intervention is a signal (P9); corrections are the evidence trust calibration needs, and routing them into the existing flywheel avoids a parallel learning store.
