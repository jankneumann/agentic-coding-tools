# Collapse the mechanical preamble into a session-start tool

> Parent roadmap: `skill-rightsizing`
> Change ID: `collapse-mechanical-preamble-session-start`
> Effort: L
> Priority: 1

## Summary

Replace the coordinator detection, tier selection, worktree setup, parent-branch resolution and worker-vendor recording steps with a single command returning structured state, and reduce the corresponding prose in all seven skills that carry it.

## Dependencies

- `ri-11`

## Acceptance Outcomes

- One command returns tier, tier rationale, worktree path, worktree branch, feature branch and worker vendor as JSON.
- Tier-selection logic exists in exactly one place and is unit tested.
- The seven affected skills no longer restate coordinator detection or tier selection.
- Replay results for the affected skills are non-inferior to the ri-09 baseline.

## Rationale

Roughly 150 lines per large skill are procedure transcribed into English with no decisions in it, duplicated seven times. Collapsing it turns tier selection into unit-testable Python and removes an entire class of drift.
