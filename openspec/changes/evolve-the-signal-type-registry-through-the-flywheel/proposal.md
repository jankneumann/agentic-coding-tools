# Evolve the signal-type registry through the flywheel

> Parent roadmap: `closed-loop-learning`
> Change ID: `evolve-the-signal-type-registry-through-the-flywheel`
> Effort: S
> Priority: 3

## Summary

Teach improve-harness to propose new signal types and detection-prompt refinements from clustered capability gaps, versioning each registry update so the taxonomy itself learns through the scheduled flywheel.

## Dependencies

- `ri-01`
- `ri-02`

## Acceptance Outcomes

- A scheduled improve-harness run over clustered capability gaps emits proposed signal-type additions or detection-prompt refinements as registry updates.
- Each accepted update produces a new registry version, and prior versions remain auditable.
- Applying a proposed registry update requires no skill-code change.

## Rationale

The proposal makes the registry a living taxonomy updated by the flywheel rather than a static list, closing the loop between recorded capability gaps and future detection coverage.
