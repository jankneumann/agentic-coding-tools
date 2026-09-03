# Tasks: route-supervise-gates-through-the-approval-gate-service

Sizes per the plan-feature Task Sizing Reference. No task is XL; one is L and is
noted with its decomposition attempt in `design.md` (D2 splits the router into four
functions, each an M-or-smaller task below).

## 1. Contracts — ninth gate and shared console decision (wp-contracts)

- [ ] 1.1 Write tests for the `roadmap_approval` gate — enum has nine members, template validates and resolves every gate to `block`, absent posture blocks `roadmap_approval`, schemas accept it (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.1 (nine gates), .2 (absent posture), supervise.Supervisor Rehydration Record "Pending gate carries the deadline" (nine values)
  **Contracts**: contracts/schemas/trust-posture.schema.json, contracts/schemas/gate-decision.schema.json, contracts/schemas/supervisor-record.schema.json
  **Design decisions**: D1
  **Dependencies**: None
  **Files**: skills/shared/tests/test_trust_posture.py, skills/shared/tests/test_approval_gate.py, skills/tests/autopilot/test_gate_schemas.py, skills/tests/supervise/test_supervisor_record_schema.py

- [ ] 1.2 Add `Gate.ROADMAP_APPROVAL` to `shared.trust_posture` — enum member, docstring gate table, `TRUST_POSTURE.template.md` entry and "nine gates" prose (S)
  **Dependencies**: 1.1
  **Files**: skills/shared/trust_posture.py, TRUST_POSTURE.template.md

- [ ] 1.3 Grow the three canonical schemas to nine gates — `trust-posture.schema.json` `gates` properties, `gate-decision.schema.json` `gate` enum plus documented optional `decision_id`, `source`, `roadmap_id`, `change_id`, `dispatch_id`, `item_id`, `supervisor-record.schema.json` `$defs.gate` and `pendingGate.decision_id`; check the mirror schema for an embedded enum (S)
  **Dependencies**: 1.1
  **Files**: openspec/schemas/trust-posture.schema.json, openspec/schemas/gate-decision.schema.json, openspec/schemas/supervisor-record.schema.json, openspec/schemas/supervisor-record-mirror.schema.json

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests skills/tests/autopilot/test_gate_schemas.py -q`, review diff, verify scope

- [ ] 1.4 Write tests for the shared `console_decision` helper — same record shape as `runner._console_decision`, runner delegates to it, `test_gate_call_sites` treats `roadmap_approval` like `replan_required` (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.3 (call-site invariant)
  **Design decisions**: D2
  **Dependencies**: 1.2
  **Files**: skills/shared/tests/test_approval_gate.py, skills/tests/autopilot/test_gate_call_sites.py, skills/autopilot/tests/test_runner_gates.py (or nearest existing runner gate test)

- [ ] 1.5 Extract `console_decision(gate, posture, approved, note)` into `shared.approval_gate` — make `runner._console_decision` a thin delegate (S)
  **Dependencies**: 1.4
  **Files**: skills/shared/approval_gate.py, skills/autopilot/scripts/runner.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests -q` and `cd skills && uv run pytest tests/autopilot -q`, review diff, verify scope

## 2. Gate router and provenance (wp-router)

- [ ] 2.1 Write tests for `gate_router.evaluate` and `answer` — record carries `decision_id`/`source`/correlation ids, lands in the checkpoint sidecar, console answer mirrors to `standing_decisions`, hot reload reflected on next evaluate, router is the only seam (AST scan) (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.1 (auto), .2 (block + console), .3 (notify files once), .7 (only seam)
  **Contracts**: contracts/schemas/gate-decision.schema.json
  **Design decisions**: D2, D5, D6
  **Dependencies**: 1.3, 1.5
  **Files**: skills/tests/supervise/test_gate_router.py

- [ ] 2.2 Implement `gate_router.py` `evaluate`, `answer`, `require_approval_ref`, `gate_log` — default evaluator `build_default_gate(agent_id="supervise", repo_root=…)`, records via `CheckpointManager.record_gate_decision`, `approval_ref` format `gate-decision:<uuid4>` (M)
  **Dependencies**: 2.1
  **Files**: skills/supervise/scripts/gate_router.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`, review diff, verify scope

- [ ] 2.3 Write tests for `resolve_parked` — `pending_gate` re-evaluated against current posture, filed `approval_id` checked before re-filing, `policy_pause` → `escalate_resume`, unknown gate raises without recording, `BLOCKED` yields a `pending_gates` entry with 7-day block horizon (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.4 (posture flip), .5 (policy pause), .8 (unknown gate); supervise.Background Worktree Isolation "Child parks at a pending gate"
  **Design decisions**: D4
  **Dependencies**: 2.2
  **Files**: skills/tests/supervise/test_gate_router.py

- [ ] 2.4 Implement `gate_router.resolve_parked` (M)
  **Dependencies**: 2.3
  **Files**: skills/supervise/scripts/gate_router.py

- [ ] 2.5 Write tests for `ExecutionAdapter` provenance — `prepare` refuses without a resolving `roadmap_approval_ref`, `resume` rejects unresolvable / blocked / wrong-gate / wrong-dispatch references, accepted references round-trip; add `approve_roadmap` / `approve_parked` fixtures and migrate existing callers (M)
  **Spec scenarios**: supervise.Approved Roadmap Execution (both scenarios); roadmap-orchestration.Durable Delegated Attempt Ledger "Resume an authorized parked attempt"; roadmap-orchestration.Outcome-Only Resume Contract "Preserve a parked child"
  **Contracts**: contracts/schemas/delegated-dispatch-attempt.continuation.patch.json
  **Design decisions**: D3
  **Dependencies**: 2.2
  **Files**: skills/tests/supervise/test_execution.py, skills/tests/supervise/test_execution_contract.py

- [ ] 2.6 Implement the `prepare` `roadmap_approval_ref` argument and the `resume` provenance check — both via `gate_router.require_approval_ref`; add the `pattern` to `continuation.approval_ref` in the stable schema (M)
  **Dependencies**: 2.5
  **Files**: skills/supervise/scripts/execution.py, openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json, openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise -q` and `cd skills && uv run pytest tests/roadmap-runtime tests/autopilot-roadmap -q`, review diff, verify scope

- [ ] 2.7 Write tests for `cycle_state.py` `gate-check`, `gate-answer`, `gate-log` — exit codes 3/0/4, printed `pending_gates` entry validates against the record schema, `gate-log` unions sidecar and active-change `loop-state.json` records, enums imported not duplicated (S)
  **Spec scenarios**: supervise.Supervise Gate Routing.1, .2, .6 (evaluation log)
  **Design decisions**: D5, D6
  **Dependencies**: 2.4
  **Files**: skills/tests/supervise/test_cycle_state.py

- [ ] 2.8 Replace the `_GATES` / `_DISPOSITIONS` literals in `cycle_state.py` with `shared.trust_posture` imports (XS)
  **Dependencies**: 2.7
  **Files**: skills/supervise/scripts/cycle_state.py

- [ ] 2.9 Implement the `gate-check`, `gate-answer`, and `gate-log` subcommands in `cycle_state.py` (S)
  **Dependencies**: 2.8
  **Files**: skills/supervise/scripts/cycle_state.py

- [ ] 2.10 Write the end-to-end evaluation-log test — fake coordinator + in-memory evaluator drive cycle → execute → parked child → posture flip → resume; assert `gate-log` has one record per evaluate/answer and every `approval_ref` resolves (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.6; proposal acceptance outcomes 1–3
  **Design decisions**: D2–D6
  **Dependencies**: 2.9
  **Files**: skills/tests/supervise/test_gate_router_e2e.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`, review diff, verify scope

## 3. Skill text and prose-free enforcement (wp-skill-docs)

- [ ] 3.1 Write `skills/tests/supervise/test_prose_free_gates.py` — scans `skills/supervise/SKILL.md` for the three retired phrases and for any `Gate` name outside a `gate-check` / `gate-answer` / `gate-log` block (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.4
  **Dependencies**: 1.2
  **Files**: skills/tests/supervise/test_prose_free_gates.py

- [ ] 3.2 Rewrite the supervise `cycle` §5 stop and the `execute` "Approval gate" and "Reconcile and resume" sections as `gate-check` / `gate-answer` / `gate-log` protocol blocks; document the notify-with-timeout notification caveat (S)
  **Dependencies**: 3.1
  **Files**: skills/supervise/SKILL.md

- [ ] 3.3 Record the direct-invocation approval in `skills/autopilot-roadmap/SKILL.md` — run `gate-answer --roadmap <id> --gate roadmap_approval --decision approved --note "direct invocation"` before execution and pass the printed `roadmap_approval_ref` (S)
  **Dependencies**: 3.1
  **Files**: skills/autopilot-roadmap/SKILL.md

- [ ] 3.4 Add a rebase note to `add-supervisor-candidate-work-digest/proposal.md` naming the `cycle_state.py` and `SKILL.md` regions this change moved (XS)
  **Dependencies**: 3.2
  **Files**: openspec/changes/add-supervisor-candidate-work-digest/proposal.md

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise/test_prose_free_gates.py -q`, review diff, verify scope

## 4. Integration (wp-integration)

- [ ] 4.1 Run `install.sh` to resync `.claude/skills/` and `.agents/skills/` mirrors; confirm `git status` shows only mirror updates (XS)
  **Dependencies**: 3.2, 3.3
  **Files**: .claude/skills/**, .agents/skills/**

- [ ] 4.2 Run the full skills suites one process per directory as CI does — `skills/shared/tests`, `skills/tests/supervise`, `skills/tests/autopilot`, `skills/tests/autopilot-roadmap`, `skills/tests/roadmap-runtime`, `skills/autopilot/tests`, `skills/tests/ci_coverage` — plus `openspec validate route-supervise-gates-through-the-approval-gate-service --strict` (S)
  **Dependencies**: 2.10, 3.4, 4.1
  **Files**: (none)

- [ ] 4.3 Verify acceptance outcome 1 manually against a copy of the template with `roadmap_approval: auto` and `pr_creation: auto` — a dry `cycle` → `gate-check` → `execute` walk reaches dispatch with no console answer; record the `gate-log` output in `session-log.md` (S)
  **Dependencies**: 4.2
  **Files**: openspec/changes/route-supervise-gates-through-the-approval-gate-service/session-log.md
