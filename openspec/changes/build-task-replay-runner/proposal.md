# Build the archived-change task-replay runner

> Parent roadmap: `skill-rightsizing`
> Change ID: `build-task-replay-runner`
> Effort: L
> Priority: 1

## Summary

Build a runner that restores the repository to a change's pre-implementation commit, hands the agent that change's proposal.md as intent while withholding the implementation, and scores the produced diff against the change's own Given/When/Then scenarios and tests.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- The runner replays any development-split change end to end and emits a per-scenario pass/fail result.
- Replay is validated on 10 changes before the corpus is scaled to 30.
- The agent under replay has no filesystem access to the withheld implementation diff.
- Each task runs N=3 times per arm and the runner reports variance across runs.

## Rationale

The archive is a benchmark because each specification was written before its implementation and ratified at a human gate. That temporal separation is what breaks circularity, and the runner is what turns it into a measurement.
