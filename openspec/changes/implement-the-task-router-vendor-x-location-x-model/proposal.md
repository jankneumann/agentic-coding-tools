# Implement the task router (vendor x location x model)

> Parent roadmap: `repo-improvement`
> Change ID: `implement-the-task-router-vendor-x-location-x-model`
> Effort: L
> Priority: 1

## Summary

Add POST /route/task and a bridge function as a superset of /archetypes/resolve_for_phase, taking a task routing profile (phase/archetype signals, duration, scope, interactivity, secret needs, parallelism, repo shape, roadmap policy) and returning vendor, location, model, isolation, dispatch_mode, and rationale, driven by deterministic unit-testable rules versioned in routing.yaml, with every decision recorded under a routing audit event type and a local static fallback table when the coordinator is down.

## Dependencies

- `ri-04`

## Acceptance Outcomes

- Given a synthetic task profile, POST /route/task returns a deterministic, explainable decision.
- Changing routing.yaml changes decisions with no code edits.
- Every autopilot phase dispatch logs a routing record with rationale to the audit log.

## Rationale

No component ever decides where a task should run - the core gap of the proposal; putting all three axes in the coordinator's existing resolver keeps one decision point, one config file, one test surface for every harness.
