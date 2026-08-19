# Wire earned tiers into orchestrator dispatch

> Parent roadmap: `closed-loop-learning`
> Change ID: `wire-earned-tiers-into-orchestrator-dispatch`
> Effort: M
> Priority: 2

## Summary

Inject the earned maturity tier as guidance into autopilot, implement-feature, and plan-feature at dispatch time, probing tiers get low-risk separable sub-work and scouts first, mature tiers get aggressive parallel fan-out, with earned tiers only ever narrowing within the agents.yaml trust_level ceiling and TRUST_POSTURE.md gates.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- Orchestrator skills consult the tier endpoint at dispatch time, and fan-out behavior differs observably between probing and mature tiers in a gen-eval scenario driven by a synthetic ledger.
- No dispatch ever exceeds the configured trust_level or a TRUST_POSTURE.md gate regardless of earned tier.
- SKILL.md contracts remain vendor-neutral, and dispatch proceeds under static configuration (no-op degradation) when the tier endpoint is unreachable.

## Rationale

Tiers only change behavior if orchestrators consult them; this makes delegation aggressiveness a number derived from outcomes while keeping statically configured trust ceilings absolute, per the proposal's constraint.
