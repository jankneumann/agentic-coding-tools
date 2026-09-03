# Contracts: route-supervise-gates-through-the-approval-gate-service

Sub-types evaluated:

| Sub-type | Applies? | Where |
|---|---|---|
| OpenAPI | No — no HTTP endpoints are added or changed; the coordinator `/approvals/*` and `/memory/store` routes are consumed as-is via `BridgeCoordinatorClient` / `BridgeAuditSink`. | — |
| Database | No — no tables or migrations. | — |
| Events / records | **Yes** — JSON Schema deltas for the gate-decision record, the trust-posture contract, the supervisor record, and the delegated-dispatch continuation. | `schemas/` |
| Generated types | No — the consumers are Python dataclasses already present in `shared.approval_gate` and `shared.trust_posture`. | — |

## `schemas/`

These are the **target** versions of stable schemas that live under `openspec/schemas/` and
`openspec/contracts/roadmap-orchestration/schemas/`. Per the ri-03 learning ("promote any
machine-readable contract needed by live code or tests before archiving its originating
change"), the implementation edits the stable files directly; the copies here are the
review artifact and the diff target for `wp-contracts`.

| File | Stable location | Delta |
|---|---|---|
| `trust-posture.schema.json` | `openspec/schemas/trust-posture.schema.json` | `gates.roadmap_approval` added (same shape as the other eight) |
| `gate-decision.schema.json` | `openspec/schemas/gate-decision.schema.json` | `gate` enum grows to nine; optional `decision_id`, `source`, `verb` (`cycle` / `execute` / `resume`), `roadmap_id`, `change_id`, `dispatch_id`, `item_id` documented — the schema already allowed additional properties, but declaring them is what keeps implementers and tests from disagreeing about their shape |
| `gate-request.schema.json` | `openspec/schemas/gate-request.schema.json` | `gate` enum grows to nine (`test_gate_schemas.py::test_gate_enum_matches_trust_posture` pins it to `Gate`; the supervise router never writes a GateRequest, but the enum must agree) |
| `supervisor-record.schema.json` | `openspec/schemas/supervisor-record.schema.json` | `$defs.gate` enum grows to nine; `pendingGate.decision_id` optional |
| `supervisor-record-mirror.schema.json` | `openspec/schemas/supervisor-record-mirror.schema.json` | Same two edits as the canonical record schema — the mirror embeds the gate enum literally rather than referencing it |
| `delegated-dispatch-attempt.continuation.patch.json` | `openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json` (and the echo in `supervised-dispatch-request.schema.json`) | JSON Merge Patch: `continuation.approval_ref` gains the `gate-decision:<uuid>` pattern |

`approval_ref` format: `gate-decision:<decision_id>` where `decision_id` is the uuid4 stamped by
`gate_router` on the record it appended to `checkpoint.json` `gate_decisions`.

## Python surface (no schema; listed for reviewers)

`shared.approval_gate` gains three public members that the router depends on and that
`wp-contracts` lands first:

| Member | Today | After |
|---|---|---|
| `build_gate_decision_record(decision, *, phase, extra=None)` | private to `skills/autopilot/scripts/autopilot.py` | shared; `autopilot.build_gate_decision_record` delegates |
| `console_decision(gate, posture, approved, note)` | `runner._console_decision(gate, pending, …)` reading `pending["posture"]` | shared; takes the `{disposition, posture_present}` snapshot directly (the supervisor sources it from its own prior blocked record, since a parked attempt carries no posture); runner delegates |
| `ApprovalGate.check_filed(gate, approval_id, *, notified) -> ApprovalDecision \| None` | — (`_interpret_status` is private and only reachable from inside the notify poll loop) | public; same status mapping, disposition from the live posture; `None` while the coordinator reports `pending`, and also on `expired` when `notified` is `False`, so an undelivered `default_action: proceed` gate is never upgraded past `_apply_default`'s fail-closed branch; records audit for terminal decisions |
