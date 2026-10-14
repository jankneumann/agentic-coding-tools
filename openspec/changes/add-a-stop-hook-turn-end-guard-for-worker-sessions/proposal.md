# Add a Stop-hook turn-end guard for worker sessions

> Parent roadmap: `operator-front-door`
> Change ID: `add-a-stop-hook-turn-end-guard-for-worker-sessions`
> Effort: S
> Priority: 2

## Summary

A Stop hook installed in worker sessions blocks a turn from ending unless work is still in flight, a pending gate is recorded as a decision card, or loop-state is terminal; a blocked turn must report what it is waiting on.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A hook test shows a worker turn ending with no in-flight work, no pending decision card, and no terminal loop-state is blocked with a message asking the worker to state what it is waiting on.
- Hook tests show turns ending with in-flight work, with a schema-valid pending card, or with terminal loop-state are allowed through.
- The guard is installed into worker sessions only and does not fire in the Supervisor session or ordinary interactive sessions.

## Rationale

Long-lived Remote Control workers that end turns silently strand the operator with no card and no progress; this guard makes every pause legible. Depends on the card schema to recognise a recorded pending card.
