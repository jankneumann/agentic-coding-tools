# Contracts — encode-autopilot-gates-and-goal-gate-in-code

Evaluated sub-types:

- **OpenAPI** — none. No HTTP surface is introduced or modified; the coordinator
  `request_approval` / `check_approval` endpoints are consumed unchanged through
  `skills/shared/approval_gate.BridgeCoordinatorClient`.
- **Database** — none. No schema is introduced or modified.
- **Events** — three JSON Schemas under `events/`, all file-carried records rather
  than bus events, which is why they live here and not on the coordinator:
  - `gate-request.schema.json` — the pending `GateRequest` that `runner.py gate-check`
    prints and `LoopState.pending_gate` stores.
  - `gate-decision.schema.json` — one `LoopState.gate_decisions[]` entry; a superset
    of `ApprovalDecision.to_audit_record()` with the two console resolutions added.
  - `replan-request.schema.json` — `<workspace>/replan-request.json`, written by
    `autopilot-roadmap` and consumed by `/plan-roadmap --replan`.
- **Type generation** — none. The three records are consumed by Python dataclasses
  that already exist (`LoopState`, `Checkpoint`); no TypeScript consumer.

Coordination boundary: `wp-autopilot-gates` and `wp-replan` both write records
described here and are otherwise disjoint. `wp-skill-docs` documents the
`gate-check` / `gate-answer` protocol against `gate-request.schema.json` and must
not invent fields the schema lacks.
