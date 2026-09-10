# Agent-activity infinity map lens

> Parent roadmap: `codeviz`
> Change ID: `add-agent-activity-map-lens`
> Effort: M
> Priority: 8

## Summary

Pan/zoom map lens rendering the live map-state IR as spatial territories: roadmaps contain changes contain work packages, anchored to parallel-zone clusters for stable geography; agents render as badges with working/waiting/idle/stale indicators; declared scope (scoped_to) renders as a package's territory with observed touches as activity dots, making out-of-scope writes and re-touches of completed packages immediately visible. Truthful traversal only; the lens renders and traces exclusively edges present in the IR, surfacing each edge's provenance as a clickable receipt. Supports a delta view diffing two frozen snapshots and a frozen self-contained HTML export for handoffs.

## Dependencies

- `map-state-ir`
- `spa-scaffold-render`
- `lens-framework`

## Acceptance Outcomes

- The lens MUST register in the lens framework, be URL-encodable, and restore its full view state from URL alone.
- Every rendered edge MUST trace to a provenance entry in the consumed IR; selecting an edge MUST reveal its evidence pointer; the lens MUST NOT render inferred edges absent from the document.
- Agent activity indicators MUST reflect coordinator state within 10 seconds during live viewing.
- Semantic zoom MUST expose at least three levels (roadmap territories, change/ package DAG, path-level activity) with zone-anchored positions stable across reloads for unchanged topology.
- A touched edge flagged out_of_scope MUST be visually distinguished within one refresh interval, and a touch on a path scoped to a completed work package MUST raise a visible regression accent.
- A delta view MUST render added/removed/changed nodes and edges between two frozen snapshots selected by snapshot_id.
- A frozen export MUST produce a self-contained HTML document of the current view requiring no coordinator connectivity.

## Rationale

The kanban board answers what is in flight per column; nothing answers where agents are working, whether they are inside their declared scope, or what is blocked waiting on a human, in one spatial view. All required data arrives via the map-state IR; this item is the renderer.
