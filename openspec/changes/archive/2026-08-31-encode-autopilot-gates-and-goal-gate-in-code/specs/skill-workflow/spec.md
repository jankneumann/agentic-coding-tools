# skill-workflow — delta

## ADDED Requirements

### Requirement: Autopilot Gate Call Sites

The autopilot loop in `skills/autopilot/scripts/autopilot.py` SHALL evaluate every member of `skills/shared/trust_posture.Gate` through `ApprovalGate.evaluate()` at exactly one code call site each, via an injected `GateEvaluator` seam whose default is `approval_gate.build_default_gate()`. The call sites SHALL be: `gatekeeper_escalation` on the GATEKEEPER `escalate` verdict; `proposal_approval` on the PLAN → PLAN_ITERATE edge; `plan_review_convergence_failure` on PLAN_REVIEW `max_iter` and PLAN_FIX `stuck`; `validation_failure` on VALIDATE `failed` and VAL_FIX `stuck`; `escalate_resume` on the ESCALATE → `_previous_phase` edge; `pr_creation` in SUBMIT_PR before the PR is created; `merge` on the SUBMIT_PR → DONE edge. (`replan_required` is evaluated by `autopilot-roadmap`; see the `roadmap-orchestration` capability.) A `merge` decision of `proceed` SHALL record merge authorization only; the loop SHALL NOT perform a merge.

Every `ApprovalDecision` returned by a call site SHALL be appended to `LoopState.gate_decisions` as `ApprovalDecision.to_audit_record()` before the loop acts on it. The orchestrator SHALL remain the only actor that mutates `LoopState.current_phase`.

#### Scenario: Default posture parks at the same points as today
- **GIVEN** no `TRUST_POSTURE.md` exists in the repository
- **WHEN** an interactive `/autopilot <change-id>` run reaches the PLAN → PLAN_ITERATE edge
- **THEN** `ApprovalGate.evaluate(Gate.PROPOSAL_APPROVAL)` SHALL return `outcome=blocked, resolution=posture_block`
- **AND** the loop SHALL surface a `gate_pending` outcome for `proposal_approval` rather than exiting
- **AND** `current_phase` SHALL remain `PLAN` until a decision is recorded

#### Scenario: Auto posture reaches SUBMIT_PR without interaction
- **GIVEN** a `TRUST_POSTURE.md` whose eight gates are all `auto`
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

### Requirement: Console Interviewer Protocol

When a gate decision is `blocked` with `resolution=posture_block` and the loop is running host-assisted (the `runner.py` cross-process path), the loop SHALL NOT exit. It SHALL persist a `GateRequest` (gate name, phase, context, prompt text, `requested_at`) as `LoopState.pending_gate` and return the outcome `gate_pending`. `runner.py` SHALL provide `gate-check <change-id>` (prints the pending `GateRequest` as JSON conforming to `contracts/events/gate-request.schema.json`, exit 0 when one is pending, exit 3 when none) and `gate-answer <change-id> --gate <name> --decision approved|rejected [--note TEXT]` (records an `ApprovalDecision` with `resolution=console_approved` or `console_rejected`, clears `pending_gate`, and applies the corresponding transition). `gate-answer` SHALL refuse with exit 2 when no gate is pending or the gate name does not match the pending request. Decisions with resolution `notify_with_timeout`, `timeout_default_block`, or `coordinator_unreachable` SHALL park the loop (save state, exit) exactly as ESCALATE does.

#### Scenario: Host asks and answers a pending gate
- **GIVEN** `loop-state.json` with `pending_gate.gate = "proposal_approval"`
- **WHEN** the host runs `runner.py gate-check <change-id>`
- **THEN** stdout SHALL be the `GateRequest` JSON and the exit code SHALL be 0
- **WHEN** the host then runs `runner.py gate-answer <change-id> --gate proposal_approval --decision approved`
- **THEN** `LoopState.gate_decisions` SHALL gain a record with `resolution=console_approved`
- **AND** `pending_gate` SHALL be cleared
- **AND** `current_phase` SHALL become `PLAN_ITERATE`

#### Scenario: Loop cannot advance past a pending gate
- **GIVEN** `loop-state.json` with a non-null `pending_gate`
- **WHEN** `run_loop()` or `runner.py apply-outcome` is invoked for that change
- **THEN** the loop SHALL NOT transition `current_phase`
- **AND** it SHALL report the pending gate name and exit without error

#### Scenario: Rejected console decision routes to ESCALATE
- **WHEN** the host runs `gate-answer --gate proposal_approval --decision rejected --note "scope too wide"`
- **THEN** the loop SHALL enter ESCALATE with `escalation_reason` containing the gate name and the note
- **AND** the decision SHALL be recorded with `resolution=console_rejected`

#### Scenario: Mismatched gate answer is refused
- **GIVEN** `pending_gate.gate = "merge"`
- **WHEN** the host runs `gate-answer --gate proposal_approval --decision approved`
- **THEN** the command SHALL exit 2, mutate nothing, and print the pending gate name

### Requirement: Goal Gate at DONE

The loop SHALL consult `goal_gate.check_goal_gate(state, change_dir)` in `_apply_transition()` before applying any transition whose target is `DONE`, except `ESCALATE` → `abandoned`. `transition()` itself SHALL stay a pure function of `(state, outcome)`. The check SHALL return `passed` only when both hold: (a) `validate_feature.gate_logic.check_phase_status()` reports `pass` for every required section of `openspec/changes/<change-id>/validation-report.md` (and the Validation Review section when `val_review_enabled`), and (b) `LoopState.phase_history` contains an entry `{"phase": "VALIDATE", "outcome": "passed"}` whose `at` timestamp is not earlier than the report's last-modified time. When the check does not pass, `_apply_transition()` SHALL raise `GoalGateRefused` carrying the failing condition, the loop SHALL enter ESCALATE with that reason, and `LoopState.goal_gate` SHALL record the verdict. `ESCALATE` → `abandoned` SHALL record `goal_gate = {"verdict": "abandoned"}` and reach DONE.

#### Scenario: Missing VALIDATE record cannot reach DONE
- **GIVEN** `loop-state.json` hand-edited to `current_phase=SUBMIT_PR` with an empty `phase_history`
- **WHEN** the SUBMIT_PR phase returns `created`
- **THEN** `_apply_transition()` SHALL raise `GoalGateRefused("no VALIDATE passed record")`
- **AND** the loop SHALL enter ESCALATE
- **AND** `current_phase` SHALL never equal `DONE`

#### Scenario: Failed validation report cannot reach DONE
- **GIVEN** `phase_history` contains `VALIDATE: passed` but `validation-report.md` reports `**Status**: fail` for the Smoke Tests section
- **WHEN** the SUBMIT_PR → DONE edge is attempted
- **THEN** the goal gate SHALL refuse with the failing section named
- **AND** `LoopState.goal_gate.verdict` SHALL be `refused`

#### Scenario: Stale report from an earlier run is rejected
- **GIVEN** `validation-report.md` last modified after the only `VALIDATE: passed` entry's `at` timestamp
- **WHEN** the goal gate runs
- **THEN** it SHALL refuse with reason `validate record predates report`

#### Scenario: Passing evidence reaches DONE
- **GIVEN** a report whose required sections all read `pass` and a `VALIDATE: passed` history entry recorded after it
- **WHEN** the `merge` gate proceeds and SUBMIT_PR returns `created`
- **THEN** `current_phase` SHALL become `DONE` and `LoopState.goal_gate.verdict` SHALL be `passed`

#### Scenario: Abandoned escalation bypasses evidence but records it
- **WHEN** ESCALATE resolves with outcome `abandoned`
- **THEN** the loop SHALL reach DONE without consulting the validation report
- **AND** `LoopState.goal_gate` SHALL equal `{"verdict": "abandoned"}`

### Requirement: Loop State Gate Records

`LoopState` SHALL advance to `schema_version` 5, adding `gate_decisions: list[dict]` (append-only audit records from `ApprovalDecision.to_audit_record()` plus console resolutions), `pending_gate: dict | None` (a `GateRequest`), and `goal_gate: dict | None`. `load_state()` SHALL migrate v4 files by supplying empty defaults for the new fields and SHALL preserve `phase_history`.

#### Scenario: v4 loop state loads with empty gate fields
- **GIVEN** a `loop-state.json` with `schema_version: 4`
- **WHEN** `load_state()` reads it
- **THEN** the result SHALL have `schema_version=5`, `gate_decisions=[]`, `pending_gate=None`, `goal_gate=None`
- **AND** every v4 field, including `phase_history`, SHALL be unchanged

#### Scenario: Gate records survive the dataclass round-trip
- **WHEN** a state with two `gate_decisions` entries and a `pending_gate` is saved and reloaded
- **THEN** both lists SHALL be byte-identical after `save_state()` → `load_state()`

### Requirement: Prose-Free Gate Enforcement

`skills/autopilot/SKILL.md` SHALL contain no gate whose only enforcement is prose. Every section that previously instructed the model to wait, stop, or ask (proposal approval, ESCALATE resume, PR creation, merge handoff) SHALL instead instruct it to run `runner.py gate-check` and, when a gate is pending, ask the operator and record the answer with `runner.py gate-answer`. The VALIDATE outcome vocabulary in `SKILL.md` SHALL match `TRANSITIONS` (`passed` / `failed`). `skills/autopilot-roadmap/SKILL.md` SHALL replace its "Deferred: automated re-decomposition" section with the replan protocol. A test SHALL assert, over the SKILL.md text, that every occurrence of a gate name from `Gate` appears within a `runner.py gate-check` / `gate-answer` block.

#### Scenario: Grep finds no prose-only gate
- **WHEN** the test scans `skills/autopilot/SKILL.md` for the phrases `Wait for proposal approval`, `STOP — Await human approval`, and `Ask if the issue has been resolved`
- **THEN** none SHALL be present outside a `gate-check` protocol block

#### Scenario: VALIDATE vocabulary matches the transition table
- **WHEN** the test extracts the documented VALIDATE outcomes from `SKILL.md`
- **THEN** they SHALL equal the keys of `TRANSITIONS["VALIDATE"]`

#### Scenario: Mirrors resynced
- **WHEN** `install.sh` runs after the SKILL.md edits
- **THEN** `.claude/skills/autopilot/SKILL.md` and `.agents/skills/autopilot/SKILL.md` SHALL be byte-identical to `skills/autopilot/SKILL.md`
