# Promote Atomic executor to opt-in IMPLEMENT and VALIDATE

> Parent roadmap: `durable-execution`
> Change ID: `promote-atomic-executor-to-opt-in-implement-and-validate`
> Effort: L
> Priority: 4

## Summary

Promote the add-atomic-harness Level-2 workflow_dispatch.py pilot from fix-scrub to an opt-in, per-phase and per-change durable executor for IMPLEMENT and VALIDATE behind the same (outcome, handoff_id) contract, resuming interrupted runs on the same runId.

## Dependencies

- `ri-08`
- `ri-02`
- `ri-10`

## Acceptance Outcomes

- Resuming an interrupted Atomic-backed phase continues the engine run with the same runId instead of starting a new attempt.
- A recorded-fixture test shows an interrupted run does not repeat a tool marked non-replayable.
- An Atomic-backed phase produces the same metaharness-visible artifacts (phase-progress journal, effects journal, PhaseRecord) as an opaque vendor CLI phase.
- Executor selection is opt-in per phase and per change; with it disabled, behavior is identical to today's.

## Rationale

Delivers the proposal's success criterion that a durable intra-phase executor can be plugged in; consumes the result of ri-10 (the adopted add-atomic-harness change) rather than re-implementing it.
