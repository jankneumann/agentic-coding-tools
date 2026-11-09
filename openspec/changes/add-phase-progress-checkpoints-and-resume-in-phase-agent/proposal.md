# Add phase progress checkpoints and resume in phase_agent

> Parent roadmap: `durable-execution`
> Change ID: `add-phase-progress-checkpoints-and-resume-in-phase-agent`
> Effort: L
> Priority: 1

## Summary

Let phase sub-agents append bounded progress checkpoints (completed work-package tasks, review rounds, validation phases, rolling draft PhaseRecord summary) to openspec/changes/<change-id>/phase-progress/<phase>-<transition_sequence>.jsonl, and make phase_agent.py hand the latest checkpoint and draft summary to a retried sub-agent so it resumes rather than restarts.

## Dependencies

- `ri-01`
- `ri-03`

## Acceptance Outcomes

- A phase interrupted after N of M checkpointed steps resumes and performs only steps N+1..M, verified with a recording runner.
- For a step with a missing checkpoint but a started or completed effect, resume consults the effects journal and does not repeat the effect.
- Retry budget counts attempts without progress; an attempt adding at least one checkpoint does not consume budget, and a hard ceiling stops unbounded loops.
- The finalized PhaseRecord of a resumed phase has the same shape as a single-attempt PhaseRecord and passes session-log validation; the (outcome, handoff_id) driver contract is unchanged.
- Missing or corrupt progress journals fall back to retry-from-scratch with a reported warning, and loop-state.json remains the sole authority for the current phase.

## Rationale

Phase 2 resumability; closes the gap where D8 retries IMPLEMENT/IMPL_REVIEW/VALIDATE from scratch, and consults the effects journal so a checkpoint gap never repeats an irreversible action.
