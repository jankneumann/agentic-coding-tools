# Contracts — add-atomic-harness

Contract sub-types evaluated for this change:

- **OpenAPI**: not applicable — no API endpoints are introduced or modified.
- **Database**: not applicable — no schema changes.
- **Events**: one applicable interface — the workflow-executor dispatch result envelope,
  defined at `workflow-dispatch/result.schema.json`. It is the coordination boundary
  between `workflow_dispatch.py` (producer, parsing Atomic's `workflow.run.end` NDJSON
  event per empirical finding A14) and its consumers (`fix-scrub` opt-in executor, audit
  trail, tests in `skills/parallel-infrastructure`).
- **Type generation stubs**: not applicable — the envelope is consumed from Python only
  in this change; stubs can be generated at promotion time if TypeScript consumers
  appear.

The first-class provider-model-map schema (`openspec/schemas/provider-model-map.schema.json`)
is intentionally NOT modified: experimental tier maps live outside its closed enum (design
decision D1c).
