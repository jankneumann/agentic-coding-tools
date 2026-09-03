## ADDED Requirements

### Requirement: Roadmap Approval Gate

The trust-posture contract SHALL define a ninth gate, `roadmap_approval`, that fires when the supervise `cycle` verb asks the operator to authorize a roadmap's DAG of items. `shared.trust_posture.Gate` SHALL enumerate it, `TRUST_POSTURE.template.md` SHALL ship it as `block`, and every schema that embeds the gate enum — `openspec/schemas/trust-posture.schema.json`, `gate-decision.schema.json`, `gate-request.schema.json`, `supervisor-record.schema.json`, and `supervisor-record-mirror.schema.json` — SHALL accept it. An absent `TRUST_POSTURE.md` or an omitted entry SHALL resolve `roadmap_approval` to `block`. `shared.approval_gate` SHALL expose public `console_decision(gate, posture, approved, note)` and `build_gate_decision_record(decision, *, phase, extra)` helpers and an `ApprovalGate.check_filed(gate, approval_id)` method that interprets a previously filed coordinator approval with the same status mapping `evaluate` uses (`approved` → proceed, `denied` → rejected, `expired` → the default action, `pending` → no decision); `skills/autopilot/scripts/runner.py` and `autopilot.py` SHALL delegate to the shared helpers so console decisions and ledger records share one shape. The prose-free gate test SHALL cover `skills/supervise/SKILL.md` as well as `skills/autopilot/SKILL.md`.

#### Scenario: Nine gates enumerated and representable
- **WHEN** `test_trust_posture.py` enumerates `Gate` and validates a contract that sets every gate
- **THEN** there SHALL be exactly nine members including `roadmap_approval`
- **AND** the template SHALL validate and resolve every gate to `block`
- **AND** `test_gate_schemas.py::test_gate_enum_matches_trust_posture` SHALL find the same nine values in `gate-request.schema.json` and `gate-decision.schema.json`, and the supervisor-record and mirror schemas SHALL accept a `pending_gates[]` entry with `gate: roadmap_approval`

#### Scenario: Absent posture keeps roadmap approval human
- **GIVEN** no `TRUST_POSTURE.md`
- **WHEN** `ApprovalGate.evaluate(Gate.ROADMAP_APPROVAL, …)` runs
- **THEN** the decision SHALL be `BLOCKED` with resolution `posture_block` and `posture_present: false`

#### Scenario: Autopilot call-site invariant is unchanged
- **WHEN** `test_gate_call_sites.py` runs
- **THEN** each of autopilot's seven gates still has exactly one `gates.evaluate(Gate.X` call site
- **AND** `roadmap_approval`, like `replan_required`, has no call site in `autopilot.py`

#### Scenario: Grep finds no prose-only gate in the supervise skill
- **WHEN** the prose-free gate test scans `skills/supervise/SKILL.md` for the phrases `Then **stop**`, `Accept only durable roadmap-altitude approval`, and `Only a parked `pending_gate` or `policy_pause` may resume with a durable `approval_ref``
- **THEN** none SHALL be present outside a `gate-check` / `gate-answer` / `gate-log` protocol block
- **AND** every occurrence of a `Gate` name in that file SHALL be inside such a block

#### Scenario: Late coordinator answer is interpreted by the gate service
- **GIVEN** an `ApprovalGate` whose coordinator reports a previously filed approval as `approved`
- **WHEN** `check_filed(Gate.ROADMAP_APPROVAL, approval_id)` is called
- **THEN** it SHALL return a decision with outcome `proceed`, resolution `approved`, and that `approval_id`, and SHALL record it to the audit sink
- **AND** when the coordinator reports `pending` it SHALL return `None` and record nothing
- **AND** when the coordinator is unreachable it SHALL return a `BLOCKED` / `coordinator_unreachable` decision rather than raise
