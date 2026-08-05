# Add typed cross-roadmap edges to the roadmap schema

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `add-typed-cross-roadmap-edges-to-the-roadmap-schema`
> Effort: M
> Priority: 2

## Summary

Extend the roadmap schema with an item_ref form (<roadmap-id>:<item-id>) and two typed edge fields: external_depends_on (cross-workspace sequencing) and superseded_by, plus a superseded item status. Extend the validator to resolve refs across all roadmap workspaces, enforce referential integrity and acyclicity repo-wide, and detect duplicate change_ids across roadmaps.

## Dependencies

- None

## Acceptance Outcomes

- external_depends_on and superseded_by accept <roadmap-id>:<item-id> refs and the validator resolves them across all roadmap workspaces, failing on unresolvable refs.
- Repo-wide validation detects a dependency cycle that spans two roadmaps and a change_id used by two roadmaps.
- The seven symphony supersessions and the always-on ri-06 -> supervisor ri-04 edge are expressed as typed edges, replacing their prose blocked_by encodings.
- An item whose only blocker is an external prerequisite becomes ready automatically when that prerequisite completes, with no manual status edit, covered by a test.

## Rationale

Cross-roadmap relations are unrepresentable today: sequencing is faked with a blocked status plus prose blocked_by, and supersession has no representation at all — the symphony audit had to record seven supersessions in a markdown table. Untraversable edges cannot auto-unblock, so every external prerequisite needs a manual status flip nothing enforces.
