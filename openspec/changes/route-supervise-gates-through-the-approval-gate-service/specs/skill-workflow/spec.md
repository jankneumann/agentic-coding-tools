## ADDED Requirements

### Requirement: Roadmap Approval Gate

The trust-posture contract SHALL define a ninth gate, `roadmap_approval`, that fires when the supervise `cycle` verb asks the operator to authorize a roadmap's DAG of items. `shared.trust_posture.Gate` SHALL enumerate it, `TRUST_POSTURE.template.md` SHALL ship it as `block`, and `openspec/schemas/trust-posture.schema.json`, `openspec/schemas/gate-decision.schema.json`, and `openspec/schemas/supervisor-record.schema.json` SHALL accept it. An absent `TRUST_POSTURE.md` or an omitted entry SHALL resolve `roadmap_approval` to `block`. `shared.approval_gate` SHALL expose a public `console_decision(gate, posture, approved, note)` helper, and `skills/autopilot/scripts/runner.py` SHALL delegate its in-conversation answers to it so console decisions share one record shape. The prose-free gate test SHALL cover `skills/supervise/SKILL.md` as well as `skills/autopilot/SKILL.md`.

#### Scenario: Nine gates enumerated and representable
- **WHEN** `test_trust_posture.py` enumerates `Gate` and validates a contract that sets every gate
- **THEN** there SHALL be exactly nine members including `roadmap_approval`
- **AND** the template SHALL validate and resolve every gate to `block`

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
