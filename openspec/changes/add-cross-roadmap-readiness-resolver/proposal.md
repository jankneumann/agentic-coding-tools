# Add cross-roadmap readiness resolver

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `add-cross-roadmap-readiness-resolver`
> Effort: S
> Priority: 2

## Summary

Promote _get_ready_items out of autopilot-roadmap into roadmap-runtime and extend it across workspaces: walk every openspec/roadmaps/*/roadmap.yaml plus its checkpoint, resolve cross-roadmap blocked_by edges, and emit one ranked ready-now list with priority ordering and a staleness signal.

## Dependencies

- None

## Acceptance Outcomes

- A single command returns the ranked ready-now list across all roadmap workspaces, each entry carrying roadmap id, item id, priority, and effort.
- Cross-roadmap blocked_by edges suppress items whose external prerequisite is incomplete, covered by a test using the always-on ri-06 / supervisor ri-04 pair.
- The resolver reads only roadmap.yaml and checkpoint state; two runs with no state change produce identical output.
- _get_ready_items has exactly one definition, imported by both autopilot-roadmap and the resolver.

## Rationale

Readiness is computed per-roadmap, in-process, and thrown away, so no artifact answers "what is executable across the repo right now" and every session re-derives it ad hoc. The resolver is the prerequisite that lets a materialized queue be a projection rather than a second source of truth.
