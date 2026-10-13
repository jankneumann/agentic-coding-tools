# Add git-native plan-time collision detection

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `plan-time-collision-detection`
> Effort: M
> Priority: 2

## Summary

Add a scanner that reads openspec/changes/* spec deltas and contracts/ across open PRs and remote branches, classifies collisions by level (intent, requirement, contract, file) with the owners involved, and run it from /plan-feature and /supervise intake.

## Dependencies

- `ri-02`
- `ri-05`

## Acceptance Outcomes

- When two open changes modify the same Requirement heading of a capability, the second /plan-feature run reports the collision, the other change, and its owner before tasks are generated.
- The scanner produces results with only a git remote available and no coordinator.
- Each reported collision is classified as intent, requirement, contract, or file level.
- An unavailable or failing scanner emits a warning and never blocks planning.
- The simulation harness's same-requirement scenario flips from not-detected to detected.

## Rationale

P7 requires collisions to surface at plan time, at the highest abstraction level, when they are still a conversation; the constraints require planning-time detection to work with only the git remote.
