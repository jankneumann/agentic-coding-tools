# Build flagged behavioral drift monitor

> Parent roadmap: `closed-loop-learning`
> Change ID: `build-flagged-behavioral-drift-monitor`
> Effort: L
> Priority: 4

## Summary

Adapt Abacus tethering as an off-by-default drift check, derive an intent snapshot at session start from the loaded handoff and active goal or change proposal, then have a step-counting hook periodically compare recent user prompts, assistant text, and tool-call names (never tool outputs) against the intent using an economy-tier model, with a reserved window share for user prompts. An off-track verdict injects a course correction for a bounded number of turns, surfaces it visibly in the transcript, and records a failure_type:scope_violation candidate to episodic memory.

## Dependencies

- `ri-05`
- `ri-09`

## Acceptance Outcomes

- The check window never includes tool outputs and always reserves the configured fixed share for user prompts, so a long build phase cannot flush them out.
- An off-track verdict produces a course correction injected for at most the bounded number of subsequent turns, surfaced visibly in the transcript, and recorded to episodic memory as a failure_type:scope_violation candidate.
- Per-check cost is bounded and attributed in usage accounting.
- The feature is off by default behind a flag and degrades to a no-op when the coordinator or hook surface is unavailable.

## Rationale

Drift between stated intent and actual activity is otherwise caught only by humans; the proposal sequences this last and behind a flag because it injects steering context and must earn enablement through evaluation.
