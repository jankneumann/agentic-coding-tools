# Inject recalled lessons with Abacus recall economics

> Parent roadmap: `closed-loop-learning`
> Change ID: `inject-recalled-lessons-with-abacus-recall-economics`
> Effort: M
> Priority: 1

## Summary

On a confident, format-conforming verdict, inject the lessons mapped to the detected signal types as context at the point of failure. Adopt the Abacus recall economics unchanged, lesson strength decays with a 14-day half-life, recall cooldown shrinks from 4 hours toward 5 minutes as strength grows, and the strongest lessons are force-recalled after two consecutive failed tool calls, all under a per-turn injection cap.

## Dependencies

- `ri-04`

## Acceptance Outcomes

- A confident verdict injects the mapped lessons at the point of failure; malformed or low-confidence verdicts produce no injection.
- A lesson unencountered for four weeks measurably drops below half its recorded strength and stops surfacing except on force-recall.
- Force-recall of the strongest lessons triggers after two consecutive failed tool calls.
- Injection volume never exceeds the cooldown schedule or the per-turn cap in any session.
- The mechanism ships off by default pending the ri-06 evaluation gate.

## Rationale

Injection at the point of failure is the one place the model is guaranteed to be looking; the decay, cooldown, and force-recall economics bound injection volume so recall cannot become context pollution, per the proposal's constraints.
