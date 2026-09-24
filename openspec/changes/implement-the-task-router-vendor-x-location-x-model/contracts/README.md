# DG-04 routing contract overlay

These contracts extend, rather than replace, the dg-00 model-routing contract at
`openspec/changes/add-adaptive-model-router/contracts/openapi/v1.yaml`.

- `openapi/v1.1.yaml` pins the additive `routing_profile`, `assignment`, and
  `provenance` fields on `POST /routing/select_model`.
- `config/routing.schema.json` is the schema for the deployed, versioned
  `agent-coordinator/routing.yaml`.
- `events/routing-decision.schema.json` pins the sanitized, link-only coordinator audit
  event.
- `events/routing-decision-record.schema.json` pins the bounded authoritative
  `routing_decisions` row and strips permissive legacy task-signal extras.

The existing `selected.vendor/model/endpoint_kind` fields keep their dg-00 meaning.
No `POST /route/task` operation exists.
