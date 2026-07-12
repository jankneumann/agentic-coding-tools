# Contracts — add-merge-plan-orchestration

Contract sub-types evaluated for this change:

| Sub-type | Applicable? | Artifact / Reason |
|----------|-------------|-------------------|
| **Data schema** | ✅ Yes | `schemas/merge-plan.schema.json` — the durable merge-plan artifact. This is the coordination boundary between the analysis round (producer) and plan-driven execution (consumer). |
| Event contract | ⏸ Phase 2 | Event-driven re-validation (`event_bus` "main advanced → re-validate {X,Y}") is specified in `design.md` D4 but implemented in the follow-on change; its payload schema will be added there. |
| OpenAPI | ⏸ Phase 2 | Coordinator plan endpoints (system-of-record tier) are Phase 2; their request/response schemas + auth scope (design.md D10) land with that change. |
| Database schema | ❌ No (Phase 1) | Phase 1 file tier has no DB. Phase 2 models plan nodes as a `work_queue` extension (existing tables) rather than new schema. |
| Type-gen stubs | ❌ No | Python-only consumer; models derived directly from `merge-plan.schema.json` at implementation time. |

Phase 1 ships exactly one contract: the plan schema. It is validated in tests (a produced
`merge-plan.json` MUST validate against it) so producer and consumer cannot drift.
