# Tasks: route-supervise-gates-through-the-approval-gate-service

Sizes per the plan-feature Task Sizing Reference. No task is XL; one is L and is
noted with its decomposition attempt in `design.md` (D2 splits the router into four
functions, each an M-or-smaller task below).

## 1. Contracts — ninth gate and shared console decision (wp-contracts)

- [ ] 1.1 Write tests for the `roadmap_approval` gate — enum has nine members, template validates and resolves every gate to `block`, absent posture blocks `roadmap_approval`, all five gate-bearing schemas (`trust-posture`, `gate-decision`, `gate-request`, `supervisor-record`, `supervisor-record-mirror`) accept it and `test_gate_enum_matches_trust_posture` stays pinned to `Gate` (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.1 (nine gates in every schema), .2 (absent posture), supervise.Supervisor Rehydration Record "Pending gate carries the deadline" (nine values)
  **Contracts**: contracts/schemas/trust-posture.schema.json, contracts/schemas/gate-decision.schema.json, contracts/schemas/gate-request.schema.json, contracts/schemas/supervisor-record.schema.json, contracts/schemas/supervisor-record-mirror.schema.json
  **Design decisions**: D1
  **Dependencies**: None
  **Files**: skills/shared/tests/test_trust_posture.py, skills/shared/tests/test_approval_gate.py, skills/tests/autopilot/test_gate_schemas.py, skills/tests/supervise/test_supervisor_record_schema.py

- [ ] 1.2 Add `Gate.ROADMAP_APPROVAL` to `shared.trust_posture` — enum member, docstring gate table, `TRUST_POSTURE.template.md` entry and "nine gates" prose (S)
  **Dependencies**: 1.1
  **Files**: skills/shared/trust_posture.py, TRUST_POSTURE.template.md

- [ ] 1.3 Grow the five gate-bearing canonical schemas to nine gates — `trust-posture.schema.json` `gates` properties; `gate-decision.schema.json` `gate` enum plus documented optional `decision_id`, `source`, `verb`, `roadmap_id`, `change_id`, `dispatch_id`, `item_id`; `gate-request.schema.json` `gate` enum; `supervisor-record.schema.json` and `supervisor-record-mirror.schema.json` `$defs.gate` and `pendingGate.decision_id` (both embed the enum literally and both `pendingGate` defs are `additionalProperties: false`) (S)
  **Dependencies**: 1.1
  **Files**: openspec/schemas/trust-posture.schema.json, openspec/schemas/gate-decision.schema.json, openspec/schemas/gate-request.schema.json, openspec/schemas/supervisor-record.schema.json, openspec/schemas/supervisor-record-mirror.schema.json

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests skills/tests/autopilot/test_gate_schemas.py -q`, review diff, verify scope

- [ ] 1.4 Write tests for the shared record helpers — `console_decision(gate, posture, approved, note)` produces the same record shape as `runner._console_decision`; `build_gate_decision_record` produces byte-identical records to today's `autopilot.build_gate_decision_record`; `ApprovalGate.check_filed(gate, approval_id)` maps `approved`/`denied`/`expired`/`pending` exactly as `_interpret_status` does (returning `None` for pending) and records audit for terminal decisions; runner and autopilot delegate to the shared helpers (existing `test_console_interviewer.py` cases stay green); `test_gate_call_sites` lists `roadmap_approval` next to `replan_required` as a non-autopilot gate (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.3 (call-site invariant), .5 (late coordinator answer)
  **Design decisions**: D2, D4
  **Dependencies**: 1.2
  **Files**: skills/shared/tests/test_approval_gate.py, skills/tests/autopilot/test_gate_call_sites.py, skills/tests/autopilot/test_console_interviewer.py

- [ ] 1.5 Move `build_gate_decision_record` and `console_decision` into `shared.approval_gate` and add `ApprovalGate.check_filed` — `autopilot.build_gate_decision_record` and `runner._console_decision` become thin delegates (autopilot call sites untouched) (S)
  **Dependencies**: 1.4
  **Files**: skills/shared/approval_gate.py, skills/autopilot/scripts/runner.py, skills/autopilot/scripts/autopilot.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests -q` and `cd skills && uv run pytest tests/autopilot -q`, review diff, verify scope

## 2. Gate router and provenance (wp-router)

- [ ] 2.1 Write tests for `gate_router.evaluate` and `answer` — record carries `decision_id`/`source`/`verb`/correlation ids, lands in the checkpoint sidecar, console answer mirrors to `standing_decisions`, hot reload reflected on next evaluate, prior-record rule (a `proceed` record for the same subject key is reused without evaluating; an open `posture_block` is re-surfaced with the same `decision_id`/`deadline` unless the disposition changed; a blocked record with an `approval_id` goes through `check_filed` before anything is re-filed; a `rejected` record is terminal until the subject key changes or `gate-answer` runs), `roadmap_fingerprint` changes on a DAG edit but not on item completion, originating `gate-answer` accepted only for `roadmap_approval`, projection into the mirror (blocked → `pending_gates` entry keyed by `decision_id`; proceed → entry removed and `roadmap_approval` standing decision upserted; reuse → mirror untouched, `written_at` preserved), router is the only seam (AST scan) (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.1 (auto), .2 (block + console), .3 (notify waits, late answer), .4 (ask once), .5 (originating console answer), .9 (only seam), .11 (projection); supervise.Supervisor Rehydration Record "Mirror write preserves unchanged-cycle idempotency"
  **Contracts**: contracts/schemas/gate-decision.schema.json, contracts/schemas/supervisor-record-mirror.schema.json
  **Design decisions**: D2, D4, D5, D6, D7
  **Dependencies**: 1.3, 1.5
  **Files**: skills/tests/supervise/test_gate_router.py

- [ ] 2.2 Implement `gate_router.py` `evaluate`, `answer`, `require_approval_ref`, `gate_log`, `roadmap_fingerprint`, and the mirror projection — default evaluator `build_default_gate(agent_id="supervise", repo_root=…)`, records via `CheckpointManager.record_gate_decision`, `approval_ref` format `gate-decision:<uuid4>`, prior-record rule per D4 step 0, projection through the existing `cycle_state.write_mirror` per D7 (M)
  **Dependencies**: 2.1
  **Files**: skills/supervise/scripts/gate_router.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`, review diff, verify scope

- [ ] 2.3 Write tests for `resolve_parked` — `pending_gate` re-evaluated against the current posture (the child snapshot carries no `approval_id`; a flip to `auto` resumes with no console answer), a prior router record for the same `dispatch_id` follows the prior-record rule, `policy_pause` → `escalate_resume`, unknown gate raises without recording, `BLOCKED` yields a `pending_gates` entry whose `deadline` is `requested_at + timeout_seconds` when an approval was filed and `+ 7 days` otherwise (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.6 (posture flip), .7 (policy pause), .10 (unknown gate); supervise.Background Worktree Isolation "Child parks at a pending gate"
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

- [ ] 2.7 Write tests for `cycle_state.py` `gate-check`, `gate-answer`, `gate-log` — exit codes 3 (proceed, including a reused decision) / 0 (`posture_block`) / 4 (terminal block: `rejected`, `timeout_default_block`, `coordinator_unreachable`), printed `pending_gates` entry validates against the record schema, `gate-answer --gate roadmap_approval` originates a record and prints `roadmap_approval_ref` while `gate-answer` for any other gate is refused without a parked record, `gate-log --roadmap R` unions the sidecar with the `loop-state.json` records of R's item change_ids only, a `--dry-run` guard is not needed because the SKILL never runs `gate-check` under `--dry-run` (assert the subcommand has no `--dry-run` flag), enums imported not duplicated (S)
  **Spec scenarios**: supervise.Supervise Gate Routing.1, .2, .5, .8 (evaluation log)
  **Design decisions**: D5, D6
  **Dependencies**: 2.4
  **Files**: skills/tests/supervise/test_cycle_state.py

- [ ] 2.8 Replace the `_GATES` / `_DISPOSITIONS` literals in `cycle_state.py` with `shared.trust_posture` imports (XS)
  **Dependencies**: 2.7
  **Files**: skills/supervise/scripts/cycle_state.py

- [ ] 2.9 Implement the `gate-check`, `gate-answer`, and `gate-log` subcommands in `cycle_state.py` (S)
  **Dependencies**: 2.8
  **Files**: skills/supervise/scripts/cycle_state.py

- [ ] 2.10 Write the end-to-end evaluation-log test — fake coordinator + in-memory evaluator drive cycle → execute → parked child → posture flip → resume, plus a second cycle that reuses the roadmap approval and honours a late coordinator answer; assert `gate-log` has one record per evaluate/answer/`check_filed` decision (and none for reuse or re-surface), and every `approval_ref` resolves (M)
  **Spec scenarios**: supervise.Supervise Gate Routing.8; proposal acceptance outcomes 1–3
  **Design decisions**: D2–D6
  **Dependencies**: 2.9
  **Files**: skills/tests/supervise/test_gate_router_e2e.py

- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`, review diff, verify scope

## 3. Skill text and prose-free enforcement (wp-skill-docs)

- [ ] 3.1 Write `skills/tests/supervise/test_prose_free_gates.py` — scans `skills/supervise/SKILL.md` for the three retired phrases and for any `Gate` name outside a `gate-check` / `gate-answer` / `gate-log` block (S)
  **Spec scenarios**: skill-workflow.Roadmap Approval Gate.4
  **Dependencies**: 1.2
  **Files**: skills/tests/supervise/test_prose_free_gates.py

- [ ] 3.2 Rewrite the supervise `cycle` §5 stop and the `execute` `### Approval gate` and `### Reconcile and resume` sections as `cycle_state.py gate-check` / `gate-answer` / `gate-log` protocol blocks (exit 3/0/4 semantics, the `notify_with_timeout` wait of up to `timeout_seconds`, the ri-05 undelivered-notification caveat, `gate-check` never under `--dry-run`, `execute` opening with `gate-check` whose exit-3 record supplies `roadmap_approval_ref`); change the final-record step to re-select the prior with `rehydrate --handoff "$SUPERVISE_HANDOFF"` instead of `supervisor-record --prior "$SUPERVISE_RECORD"` so the router's mirror projection survives (D7); keep the headings `test_workflow_contract.py` slices on and its pinned phrase ``durable `approval_ref` `` (write "a durable `approval_ref` of the form `gate-decision:<decision_id>`"), or update that test in the same commit (S)
  **Dependencies**: 3.1
  **Files**: skills/supervise/SKILL.md, skills/tests/supervise/test_workflow_contract.py

- [ ] 3.3 Record the direct-invocation approval in `skills/autopilot-roadmap/SKILL.md` — run `gate-answer --roadmap <id> --gate roadmap_approval --decision approved --note "direct invocation"` before execution and pass the printed `roadmap_approval_ref` (S)
  **Dependencies**: 3.1
  **Files**: skills/autopilot-roadmap/SKILL.md

- [ ] 3.4 Add a rebase note to `add-supervisor-candidate-work-digest/proposal.md` naming the `SKILL.md` §5 protocol block this change introduced (that change rewrites `cycle` §2–§5 and leaves `cycle_state.py` untouched, so `cycle_state.py` needs no note) (XS)
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
