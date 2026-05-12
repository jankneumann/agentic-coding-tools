# Contracts: add-decision-index

## No contract sub-types apply

This change does not introduce or modify any of the sub-types that warrant machine-readable interface contracts:

| Sub-type | Applicable? | Rationale |
|---|---|---|
| **OpenAPI** (HTTP endpoints) | No | Feature has no HTTP surface. `make decisions` is a local build target; the emitter writes files, not responses. |
| **Database schema** | No | No database tables added or modified. The emitter reads markdown from `openspec/changes/` and writes markdown to `docs/decisions/`. |
| **Event payloads** | No | No events emitted or consumed. |
| **Generated types** | No | No types generated for downstream consumers. The `TaggedDecision` dataclass is internal to `decision_index.py`; it is not exported or versioned as an external contract. |

## What *does* act as a contract for this change

The **Phase Entry tag syntax** defined in `../specs/skill-workflow/spec.md` is a human-readable contract between:

- **Producers** — workflow skills that append Phase Entries to `session-log.md` (plan-feature, implement-feature, iterate-on-plan, iterate-on-implementation, validate-feature, cleanup-feature)
- **Consumer** — the per-capability emitter in `skills/explore-feature/scripts/decision_index.py`

The contract is specified as a regex in `../design.md §Data model` and enforced by the tests in phase 1 and phase 2 of `../tasks.md`. Changes to the tag syntax would require a coordinated update to both the producers (skills) and the consumer (emitter) — which is exactly what the `skill-workflow` spec delta captures.

## If contracts become necessary later

If the emitter is ever exposed over HTTP (e.g., as part of a future docs-service), the OpenAPI contract would be added here and the emitter factored behind a stable function signature. This is out of scope for the current change.
