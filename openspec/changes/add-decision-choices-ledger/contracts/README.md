# Contracts: add-decision-choices-ledger

Contract sub-types evaluated for this change:

- **OpenAPI**: not applicable — no API endpoints introduced or modified.
- **Database**: not applicable — no database schemas introduced or modified.
- **Events**: not applicable — no runtime events emitted. Deliberately no
  `ledger.changed`-style SSE event (that name is reserved by the in-flight
  `ambient-review-ledger` change; a `choices.changed` event is a possible
  future composition, out of scope here).
- **Data-file schema**: **applicable** — `decision-choices.schema.json` in
  this directory is the coordination boundary between the auditor-skill and
  workflow-hook work packages. During implementation (task 1.2) it lands
  canonically at `openspec/schemas/decision-choices.schema.json`, following
  the `review-findings.schema.json` / `consensus-report.schema.json`
  convention; this copy is frozen for the duration of package execution.

Type-generation stubs: not applicable — consumers are Python scripts using
`jsonschema` validation directly, matching existing ledger/finding consumers.
