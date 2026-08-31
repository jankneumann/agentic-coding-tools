# Change Context: encode-autopilot-gates-and-goal-gate-in-code

Generated at validation time (Phase 3). The change was implemented before this
artifact was created, so Phase 1/2 columns are reconstructed from the spec deltas
and `git diff --name-only main...HEAD` rather than filled incrementally.

**Contract Ref** is `---` for every row: this change's contracts are three
file-carried JSON Schemas under `contracts/events/`, and no *traced contract
document* (one declaring a `traceability`/`x-traceability` block, per
trace-requirements-to-contracts D8) cites these requirements. The change-scoped
traceability gate confirms this — it passes with zero violations attributable to
this change. The schemas are still enforced: `test_gate_schemas.py` validates
them and pins their enums to `trust_posture.Gate` and
`approval_gate.Resolution` in code.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Autopilot Gate Call Sites — every `Gate` member has exactly one `evaluate()` call site via an injected evaluator; decisions appended before the loop acts | --- | D1, D2 | skills/autopilot/scripts/autopilot.py | skills/tests/autopilot/test_gate_call_sites.py | pass 9df61c81 |
| skill-workflow.2 | specs/skill-workflow/spec.md | Console Interviewer Protocol — `posture_block` parks with a GateRequest; `gate-check`/`gate-answer` record the operator's decision; loop cannot advance while pending | --- | D3 | skills/autopilot/scripts/runner.py, skills/autopilot/scripts/autopilot.py | skills/tests/autopilot/test_console_interviewer.py, skills/tests/autopilot/test_gate_evaluate_cli.py, skills/tests/autopilot/test_runner_cli.py | pass 9df61c81 |
| skill-workflow.3 | specs/skill-workflow/spec.md | Goal Gate at DONE — DONE refused unless the validation report passes AND a VALIDATE:passed history entry postdates it | --- | D5, D6 | skills/autopilot/scripts/goal_gate.py, skills/autopilot/scripts/autopilot.py | skills/tests/autopilot/test_goal_gate.py, skills/tests/autopilot/test_gate_call_sites.py | pass 9df61c81 |
| skill-workflow.4 | specs/skill-workflow/spec.md | Loop State Gate Records — schema_version 5 adds gate_decisions, pending_gate, goal_gate; v4 migrates with empty defaults | --- | D7 | skills/autopilot/scripts/autopilot.py | skills/tests/autopilot/test_loop_state.py, skills/tests/autopilot/test_apply_outcome_contract.py, skills/tests/phase-record-compaction/test_loopstate_schema.py | pass 9df61c81 |
| skill-workflow.5 | specs/skill-workflow/spec.md | Prose-Free Gate Enforcement — no gate enforced only by prose; VALIDATE vocabulary matches TRANSITIONS; mirrors resynced | --- | D9 | skills/autopilot/SKILL.md, skills/autopilot-roadmap/SKILL.md, skills/plan-roadmap/SKILL.md | skills/tests/autopilot/test_prose_free_gates.py | pass 9df61c81 |
| roadmap-orchestration.1 | specs/roadmap-orchestration/spec.md | Adaptive Roadmap Execution — explicit `replan: true` produces replan_required; the gate fires once per failure; PROCEED emits replan-request.json; orchestrator never replans itself | --- | D8 | skills/roadmap-runtime/scripts/checkpoint.py, skills/autopilot-roadmap/scripts/orchestrator.py | skills/tests/roadmap-runtime/test_checkpoint_replan.py, skills/tests/autopilot-roadmap/test_replan_gate.py | pass 9df61c81 |
| roadmap-orchestration.2 | specs/roadmap-orchestration/spec.md | Proposal Decomposition — replan mode emits the affected subgraph excluding preserved statuses; preserved items and learnings survive byte-identical | --- | D8 | skills/plan-roadmap/scripts/decomposer.py | skills/tests/plan-roadmap/test_replan_scope.py | pass 9df61c81 |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | One injected `GateEvaluator` seam, lazily defaulting to `build_default_gate()` | `autopilot.py` `_GateSession` | Matches the loop's existing injection style; keeps import working without a coordinator; stays fail-closed |
| D2 | One call site per gate, in the handler owning its context | seven `gates.evaluate(Gate.X` sites | Context (PR URL, proposal path) exists only in the handler; an AST test can then enumerate the enum |
| D3 | `gate_pending` is an outcome, not a phase; the ask is host-executed | `runner.py gate-check/gate-answer` | Host-assisted invariant forbids scripts asking a human; enforcement stays in code |
| D5 | Goal gate needs report evidence AND a run-fresh history entry | `goal_gate.py` | A report can be stale; a history entry alone is self-reported |
| D6 | `_apply_transition` is the single enforcement point | `autopilot.py` | Every path into DONE passes through it, including hand-edited state |
| D7 | LoopState v5 with three new fields | `autopilot.py` | Additive; v4 migrates with empty defaults |
| D8 | `replan_required` produced only on an explicit signal, consumed via a file | `checkpoint.py`, `orchestrator.py`, `decomposer.py` | No classifier exists; a file keeps the orchestrator free of network calls |
| D9 | SKILL.md prose replaced by the protocol, pinned by a test | three SKILL.md files | Prose drifts; a test that enumerates the Gate enum does not |

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 7 requirements have at least one test
- **Evidence collected**: 7/7 requirements have pass/fail evidence
- **Gaps identified**: None. All 26 new spec-scenario obligations have tests; the 9 carried-forward scenarios are unchanged pre-existing behaviour.
- **Deferred items**: Two open questions recorded in the Implementation phase record — whether the goal gate's DONE enforcement is reachable on the host-driven path (the same question the host-path fix answered for the gates), and that `pr_creation`'s console answer is not consumed by the in-process loop.
