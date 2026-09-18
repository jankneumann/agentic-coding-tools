# Schedule the learning pipeline run over the always-loaded surface

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `schedule-always-loaded-surface-learning-run`
> Effort: M
> Priority: 5

## Summary

Wire the scheduled learning pipeline so a recurring run executes backpass (or its port) over the memory surface, emits the gap ledger into memory, opens the proposal branch, and then runs /improve-harness over the orchestration-domain output; publish a run summary with the budget bar, edits proposed, and gaps graduated.

## Dependencies

- `ri-01`
- `ri-05`
- `ri-14`
- `ri-15`

## Acceptance Outcomes

- A scheduled workflow or routine definition exists that runs the pipeline end to end and completes on a fixture corpus in CI without manual steps.
- Each run publishes a summary containing the always-loaded token estimate, number of edits proposed, number of gaps graduated, and the interactive/non-interactive split.
- A run with no graduated gaps and a surface within budget opens no proposal branch and writes no memory entries.

## Rationale

Phase 4 and section 7: this is the concrete form of repo-improvement RI-12 (scheduled learning pipeline). It turns the one-shot rightsizing cut into a continuous maintenance loop where relevance prioritizes and the PR gate accepts.
