# Define canonical candidate-work schema

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `define-canonical-candidate-work-schema`
> Effort: M
> Priority: 2

## Summary

Define one proposal-stub JSON Schema under `openspec/schemas/` carrying provenance (source artifact, finding IDs), effort/priority estimates, and suggested change-id, and make `/prioritize-proposals` consume only this schema, rejecting non-conforming input. Upstream-compatible with the always-on proposal's Phase 6 Findings-to-Issues pipeline, which will file issues from these same stubs.

## Dependencies

- None

## Acceptance Outcomes

- A JSON Schema for candidate-work stubs exists under openspec/schemas/ with provenance, effort/priority, and suggested change-id fields.
- /prioritize-proposals validates input against the schema and rejects a deliberately non-conforming stub with a clear error.
- Schema validation is covered by tests including at least one valid and one invalid fixture.

## Rationale

One artifact per concept — a single candidate-work shape is what lets the discovery back-edge close into the roadmap without a human courier or a fourth ad-hoc format.
