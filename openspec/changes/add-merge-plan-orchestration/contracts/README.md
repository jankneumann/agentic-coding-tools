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

## Producer-enforced semantic invariants (beyond JSON Schema)

The plan is a **DAG**. JSON Schema can express per-node edge uniqueness (`depends_on`
carries `uniqueItems`) but cannot express cross-node graph properties, so the producer
(analysis round + living-amendment insertion) MUST additionally guarantee, and its tests
MUST reject violations of:

1. **Unique nodes** — each `node.pr` appears at most once across `nodes`.
2. **Edge membership** — every value in a node's `depends_on` refers to a `pr` present in
   `nodes` (no dangling edges).
3. **No self-dependency** — a node's `depends_on` does not contain its own `pr`.
4. **Acyclicity** — the dependency graph has no cycles, so a topological execution order
   always exists.

A `merge-plan.json` that is schema-valid but violates any of the above is malformed;
consumers may reject it rather than attempt execution.
