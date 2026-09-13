## MODIFIED Requirements

### Requirement: Autopilot Gate Call Sites

The autopilot loop in `skills/autopilot/scripts/autopilot.py` SHALL evaluate every member of `skills/shared/trust_posture.Gate` through `ApprovalGate.evaluate()` at exactly one code call site each, via an injected `GateEvaluator` seam whose default is `approval_gate.build_default_gate()`. The call sites SHALL be: `gatekeeper_escalation` on the GATEKEEPER `escalate` verdict; `proposal_approval` on the PLAN → PLAN_ITERATE edge; `plan_review_convergence_failure` on PLAN_REVIEW `max_iter` and PLAN_FIX `stuck`; `validation_failure` on VALIDATE `failed` and VAL_FIX `stuck`; `escalate_resume` on the ESCALATE → `_previous_phase` edge; `pr_creation` in SUBMIT_PR before the PR is created; `merge` on the SUBMIT_PR → DONE edge. (`replan_required` is evaluated by `autopilot-roadmap`, and `roadmap_approval` by the supervise skill's gate router; see the `roadmap-orchestration` and `supervise` capabilities.) A `merge` decision of `proceed` SHALL record merge authorization only; the loop SHALL NOT perform a merge.

Every `ApprovalDecision` returned by a call site SHALL be appended to `LoopState.gate_decisions` as `ApprovalDecision.to_audit_record()` before the loop acts on it. The orchestrator SHALL remain the only actor that mutates `LoopState.current_phase`.

#### Scenario: Default posture parks at the same points as today
- **GIVEN** no `TRUST_POSTURE.md` exists in the repository
- **WHEN** an interactive `/autopilot <change-id>` run reaches the PLAN → PLAN_ITERATE edge
- **THEN** `ApprovalGate.evaluate(Gate.PROPOSAL_APPROVAL)` SHALL return `outcome=blocked, resolution=posture_block`
- **AND** the loop SHALL surface a `gate_pending` outcome for `proposal_approval` rather than exiting
- **AND** `current_phase` SHALL remain `PLAN` until a decision is recorded

#### Scenario: Auto posture reaches SUBMIT_PR without interaction
- **GIVEN** a `TRUST_POSTURE.md` whose gates are all `auto` (the count is deliberately unstated here — this scenario is about the seven gates autopilot itself evaluates, not the total in `Gate`, which grows independently of this requirement)
- **WHEN** `run_loop()` executes a change whose phases all succeed
- **THEN** the run SHALL reach `SUBMIT_PR` with zero `gate_pending` outcomes
- **AND** `LoopState.gate_decisions` SHALL contain one record per evaluated gate, each with `resolution=auto`

#### Scenario: Coordinator unreachable during notify parks the loop
- **GIVEN** a posture that sets `merge` to `notify_with_timeout` with `default_action: proceed`
- **WHEN** the coordinator raises `CoordinatorUnavailable` while the `merge` gate is evaluated
- **THEN** the decision SHALL be `outcome=blocked, resolution=coordinator_unreachable`
- **AND** the loop SHALL save `loop-state.json` with `current_phase=SUBMIT_PR` and exit
- **AND** the run SHALL NOT transition to DONE

#### Scenario: Escalate resume is a gate, not a stub
- **GIVEN** `loop-state.json` with `current_phase=ESCALATE` and `previous_phase=IMPLEMENT`
- **WHEN** the loop is re-invoked
- **THEN** `Gate.ESCALATE_RESUME` SHALL be evaluated
- **AND** on `proceed` the loop SHALL transition to `IMPLEMENT`
- **AND** on `blocked` the loop SHALL remain in `ESCALATE` and record the decision

#### Scenario: Gate decision persisted before the loop acts
- **WHEN** any gate evaluation returns
- **THEN** `loop-state.json` on disk SHALL contain the decision's audit record
- **AND** only then SHALL the loop transition, park, or surface `gate_pending`

## ADDED Requirements

### Requirement: Roadmap Approval Gate

The trust-posture contract SHALL define a ninth gate, `roadmap_approval`, that fires when the supervise `cycle` verb asks the operator to authorize a roadmap's DAG of items. `shared.trust_posture.Gate` SHALL enumerate it, `TRUST_POSTURE.template.md` SHALL ship it as `block`, and every schema that embeds the gate enum — `openspec/schemas/trust-posture.schema.json`, `gate-decision.schema.json`, `gate-request.schema.json`, `supervisor-record.schema.json`, and `supervisor-record-mirror.schema.json` — SHALL accept it. An absent `TRUST_POSTURE.md` or an omitted entry SHALL resolve `roadmap_approval` to `block`. `shared.approval_gate` SHALL expose public `console_decision(gate, posture, approved, note)` and `build_gate_decision_record(decision, *, phase, extra)` helpers and an `ApprovalGate.check_filed(gate, approval_id, *, notified)` method that interprets a previously filed coordinator approval with the same status mapping `evaluate` uses (`approved` → proceed, `denied` → rejected, `expired` → the default action, `pending` → no decision), resolving the gate's disposition from the live posture and taking `notified` from the caller's prior record rather than assuming delivery, so an undelivered notification can never be upgraded from a fail-closed block to a `proceed` default; `skills/autopilot/scripts/runner.py` and `autopilot.py` SHALL delegate to the shared helpers so console decisions and ledger records share one shape. The prose-free gate test SHALL cover `skills/supervise/SKILL.md` as well as `skills/autopilot/SKILL.md`.

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
- **AND** `roadmap_approval` SHALL have exactly one call site in `skills/supervise/scripts/gate_router.py`, as `replan_required` has exactly one in the roadmap orchestrator, so excluding it from autopilot's set does not exempt it from the one-call-site invariant

#### Scenario: Grep finds no prose-only gate in the supervise skill
- **WHEN** the prose-free gate test scans `skills/supervise/SKILL.md` for the phrases `Then **stop**`, `Accept only durable roadmap-altitude approval`, and `Only a parked `pending_gate` or `policy_pause` may resume with a durable `approval_ref``
- **THEN** none SHALL be present outside a `gate-check` / `gate-answer` / `gate-log` protocol block
- **AND** every backticked or `Gate.`-qualified occurrence of a gate name in that file SHALL be inside such a block, the backtick rule being what keeps the ordinary English word `merge` in unrelated prose from reading as a gate reference
- **AND** the gates supervise is expected to name — `roadmap_approval`, `escalate_resume`, and a parked child's gate — SHALL each have such a block, and the check SHALL be keyed by `trust_posture.Gate` so a renamed member fails rather than silently disappears

#### Scenario: Late coordinator answer is interpreted by the gate service
- **GIVEN** an `ApprovalGate` whose coordinator reports a previously filed approval as `approved`
- **WHEN** `check_filed(Gate.ROADMAP_APPROVAL, approval_id, notified=True)` is called
- **THEN** it SHALL return a decision with outcome `proceed`, resolution `approved`, and that `approval_id`, and SHALL record it to the audit sink
- **AND** when the coordinator reports `pending` it SHALL return `None` and record nothing, regardless of `notified`
- **AND** when the coordinator reports `expired` and the caller passes `notified=True`, it SHALL apply the live posture's `default_action`
- **AND** when the coordinator reports `expired` and the caller passes `notified=False` — the state a `default_action: proceed` gate reaches today because `BridgeCoordinatorClient.push_notification` always returns `False` — it SHALL return `None` and leave the fail-closed block standing
- **AND** the caller SHALL supply `notified` from the gate-decision record's own persisted `notified` field, never a literal or a default, so the block-standing arm above is the one every production `roadmap_approval` timeout reaches
- **AND** when the coordinator is unreachable it SHALL return a `BLOCKED` / `coordinator_unreachable` decision rather than raise
