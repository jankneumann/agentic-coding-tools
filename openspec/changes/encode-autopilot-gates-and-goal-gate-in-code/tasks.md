# Tasks — encode-autopilot-gates-and-goal-gate-in-code

Six phases, one per work package. Test tasks precede the implementation they verify
(TDD RED → GREEN). Sizes per the plan-feature Task Sizing Reference; no task is L or XL.

Capability short names: `sw` = `skill-workflow`, `ro` = `roadmap-orchestration`.
Contracts: `contracts/events/{gate-request,gate-decision,replan-request}.schema.json`.

---

## Phase 0 — wp-contracts: schemas are the coordination boundary

- [x] 0.1 Test: each of the three event schemas is a valid JSON Schema 2020-12 document and
      the `gate-decision` `resolution` enum equals `approval_gate.Resolution` values plus the
      two console values — **XS**
      **Spec scenarios**: sw *Gate records survive the dataclass round-trip*
      **Contracts**: all three schemas
      **Design decisions**: D4
      **Dependencies**: None

- [x] 0.2 Fixtures: one valid and one invalid instance per schema under
      `skills/tests/autopilot/fixtures/gates/`, asserted by 0.1 — **XS**
      **Contracts**: all three schemas
      **Dependencies**: 0.1

- [x] Checkpoint: run `skills/tests/autopilot -k schema`, review the diff, confirm only the
      change directory and the fixtures directory changed

## Phase 1 — wp-goal-gate: the pure evidence check

- [x] 1.1 Test: `check_goal_gate` returns `passed` only when every required section reads
      `pass` AND the latest `VALIDATE` history entry is `passed` with `at >= report mtime`;
      returns `refused` naming the failing condition for: no history entry, `failed` entry,
      stale entry, a `fail` section, a `skipped` section, missing report — **S**
      **Spec scenarios**: sw *Missing VALIDATE record cannot reach DONE*, *Failed validation
      report cannot reach DONE*, *Stale report from an earlier run is rejected*, *Passing
      evidence reaches DONE*
      **Design decisions**: D5
      **Dependencies**: None

- [x] 1.2 Test: when `state.val_review_enabled`, the Validation Review section is required
      too; when not, its absence is ignored — **XS**
      **Spec scenarios**: sw *Passing evidence reaches DONE*
      **Design decisions**: D5
      **Dependencies**: None

- [x] 1.3 Implement `skills/autopilot/scripts/goal_gate.py` — `GoalGateVerdict`,
      `check_goal_gate()`, required sections from `gate_logic.resolve_required_phases`,
      mtime comparison with an injected `now` — **S**
      **Spec scenarios**: all five *Goal Gate at DONE* scenarios
      **Design decisions**: D5
      **Dependencies**: 1.1, 1.2

- [x] Checkpoint: goal-gate tests green, review the diff, confirm `goal_gate.py` imports
      `gate_logic` and nothing from `autopilot.py` except `LoopState`

## Phase 2 — wp-autopilot-gates: seam, call sites, console protocol

- [x] 2.1 Test: a v4 `loop-state.json` loads as v5 with `gate_decisions=[]`,
      `pending_gate=None`, `goal_gate=None`, all v4 fields intact; v5 round-trips
      byte-identically — **S**
      **Spec scenarios**: sw *v4 loop state loads with empty gate fields*, *Gate records
      survive the dataclass round-trip*
      **Contracts**: gate-decision, gate-request
      **Design decisions**: D7
      **Dependencies**: None

- [x] 2.2 Implement `LoopState` v5 fields, migration in `load_state`, and pass-through of the
      three keys in `apply_outcome_or_escalate` — **S**
      **Design decisions**: D7
      **Dependencies**: 2.1

- [x] 2.3 Test: `Resolution.CONSOLE_APPROVED` is a proceed resolution,
      `Resolution.CONSOLE_REJECTED` is not, and `ApprovalGate.evaluate()` never returns
      either — **XS**
      **Contracts**: gate-decision
      **Design decisions**: D4
      **Dependencies**: None

- [x] 2.4 Add the two console members to `approval_gate.Resolution` and
      `_PROCEED_RESOLUTIONS` — **XS**
      **Design decisions**: D4
      **Dependencies**: 2.3

- [x] Checkpoint: `skills/shared/tests` and `skills/tests/autopilot/test_loop_state.py`
      green, review the diff, confirm no handler logic changed yet

- [x] 2.5 Test: with a `FakeGateEvaluator`, each of the seven autopilot gates is evaluated at
      exactly its D2 site with the documented context keys; an AST walk over `autopilot.py`
      and `orchestrator.py` finds exactly one `evaluate(Gate.<X>` per `Gate` member; an
      all-`auto` evaluator runs the happy path to `SUBMIT_PR` with zero `gate_pending`; every
      decision is appended to `gate_decisions` before the transition is applied — **M**
      **Spec scenarios**: sw *Auto posture reaches SUBMIT_PR without interaction*, *Gate
      decision persisted before the loop acts*, *Escalate resume is a gate, not a stub*
      **Contracts**: gate-decision
      **Design decisions**: D1, D2
      **Dependencies**: 2.2, 2.4

- [x] 2.6 Implement the `GateEvaluator` protocol, the lazy default, and the seven call sites
      in `_phase_gatekeeper`, `_phase_plan`, `_run_phase`, `_phase_escalate`,
      `_phase_submit_pr` — **M**
      **Design decisions**: D1, D2
      **Dependencies**: 2.5

- [x] Checkpoint: `skills/autopilot/scripts/tests/test_autopilot.py` still green with no
      evaluator injected (lazy default must not be built when no gate is reached), review the
      diff, confirm `transition()` is unchanged

- [x] 2.7 Test: `posture_block` sets `pending_gate` and returns `gate_pending` without
      exiting; `notify`-family BLOCKED resolutions park like ESCALATE; `_apply_transition`
      raises `GatePending` while a gate is pending; a DONE-targeted edge with refused evidence
      raises `GoalGateRefused` and `run_loop` lands in ESCALATE with the reason;
      `ESCALATE/abandoned` reaches DONE with `goal_gate.verdict == "abandoned"`; a hand-edited
      `current_phase=SUBMIT_PR` with empty history never reaches DONE — **S**
      **Spec scenarios**: sw *Default posture parks at the same points as today*,
      *Coordinator unreachable during notify parks the loop*, *Loop cannot advance past a
      pending gate*, *Missing VALIDATE record cannot reach DONE*, *Abandoned escalation
      bypasses evidence but records it*
      **Contracts**: gate-request
      **Design decisions**: D3, D6
      **Dependencies**: 1.3, 2.6

- [x] 2.8 Implement `gate_pending` handling in `_run_phase`/`run_loop`, the `GatePending` and
      `GoalGateRefused` checks in `_apply_transition`, and the `abandoned` record — **S**
      **Design decisions**: D3, D6
      **Dependencies**: 2.7

- [x] Checkpoint: full `skills/tests/autopilot` + `skills/autopilot/scripts/tests` green,
      review the diff, confirm `phase_agent.apply_phase_outcome` still routes through
      `_apply_transition`

- [x] 2.9 Test: `runner.py gate-check` prints schema-valid JSON and exits 0/3;
      `gate-answer --decision approved` records `console_approved`, clears `pending_gate`,
      applies the edge; `rejected` enters ESCALATE with the note; a mismatched `--gate` exits
      2 and mutates nothing; `apply-outcome` refuses while a gate is pending — **S**
      **Spec scenarios**: sw *Host asks and answers a pending gate*, *Rejected console
      decision routes to ESCALATE*, *Mismatched gate answer is refused*, *Loop cannot advance
      past a pending gate*
      **Contracts**: gate-request, gate-decision
      **Design decisions**: D3, D4
      **Dependencies**: 2.8

- [x] 2.10 Implement `gate-check` and `gate-answer` subcommands in `runner.py` and the
      pending-gate refusal in `apply-outcome` — **S**
      **Design decisions**: D3
      **Dependencies**: 2.9

- [x] 2.11 Test (e2e, `test_gate_e2e.py`): with a temp `TRUST_POSTURE.md` of all `auto`, a
      scripted happy path reaches `SUBMIT_PR` with no interaction and eight `auto` records;
      with no posture file the same path stops at PLAN with `pending_gate.gate ==
      "proposal_approval"`; with `merge: notify_with_timeout` and a client raising
      `CoordinatorUnavailable`, the loop parks at `SUBMIT_PR` — **S**
      **Spec scenarios**: sw *Auto posture reaches SUBMIT_PR without interaction*, *Default
      posture parks at the same points as today*, *Coordinator unreachable during notify
      parks the loop*
      **Design decisions**: D1, D3
      **Dependencies**: 2.10

- [x] Checkpoint: e2e green, review the cumulative Phase 2 diff against `write_allow`, update
      these checkboxes

## Phase 3 — wp-replan: producer, gate, and replan scope

- [x] 3.1 Test: `fail_item(..., replan=True)` moves `approved`/`candidate` dependents to
      `replan_required` with `blocked_by` set; default keeps today's `blocked` behaviour;
      completed dependents are untouched — **S**
      **Spec scenarios**: ro *Explicit replan signal produces replan_required*, *Handle
      individual roadmap item implementation failure*
      **Design decisions**: D8
      **Dependencies**: None

- [x] 3.2 Implement the `replan` keyword in `CheckpointManager.fail_item` — **XS**
      **Design decisions**: D8
      **Dependencies**: 3.1

- [x] 3.3 Test: after a failure with `replan: true`, the orchestrator evaluates
      `Gate.REPLAN_REQUIRED` once; PROCEED writes a schema-valid `replan-request.json` and
      returns status `replan_requested` without dispatching the parked items; BLOCKED writes
      nothing, records the decision in the checkpoint, and continues; the host-assisted
      invariant test still passes — **S**
      **Spec scenarios**: ro *Replan gate proceeds and emits a request*, *Replan gate blocked
      leaves items parked*, *Orchestrator never performs the replan itself*
      **Contracts**: replan-request, gate-decision
      **Design decisions**: D1, D8
      **Dependencies**: 3.2

- [x] 3.4 Implement the gate evaluation, request writer, `Checkpoint.gate_decisions`, and
      the `replan_requested` summary status in `orchestrator.py` — **S**
      **Design decisions**: D8
      **Dependencies**: 3.3

- [x] Checkpoint: `skills/tests/roadmap-runtime` + `skills/tests/autopilot-roadmap` green,
      review the diff, confirm `models.py` is untouched

- [x] 3.5 Test: `decomposer.py replan-scope <workspace>` lists exactly the `replan_required`
      items plus transitive non-completed dependents; excludes completed, superseded, and
      unrelated items; errors clearly when no request file exists — **S**
      **Spec scenarios**: ro *Replan scope is the affected subgraph only*, *Replan without a
      request file is refused*
      **Contracts**: replan-request
      **Design decisions**: D8
      **Dependencies**: None

- [x] 3.6 Implement `replan-scope` in `decomposer.py` and the `--replan <roadmap-id>` flag
      handling (request-file check, scope emission, post-replan `validate`, request-file
      deletion) — **M**
      **Design decisions**: D8
      **Dependencies**: 3.5

- [x] 3.7 Test: a scripted replan leaves completed/superseded/in_progress items and every
      `learnings/` file byte-identical, sets re-decomposed items to `approved`, deletes the
      request file — **S**
      **Spec scenarios**: ro *Replan preserves completed items and learnings*
      **Design decisions**: D8
      **Dependencies**: 3.6

- [x] Checkpoint: `skills/tests/plan-roadmap` green, review the diff, verify scope

## Phase 4 — wp-skill-docs: de-prose the gates

- [x] 4.1 Test (`test_prose_free_gates.py`): none of the three retired phrases appears in
      `skills/autopilot/SKILL.md`; every `Gate` value mentioned appears inside a
      `gate-check`/`gate-answer` block; documented VALIDATE outcomes equal
      `TRANSITIONS["VALIDATE"].keys()`; the three mirrors are byte-identical — **S**
      **Spec scenarios**: sw *Grep finds no prose-only gate*, *VALIDATE vocabulary matches
      the transition table*, *Mirrors resynced*
      **Design decisions**: D9
      **Dependencies**: None

- [x] 4.2 Rewrite the proposal-approval (§2), ESCALATE-resume (§0), PR-creation (§8), and
      merge-handoff (§9) sections of `skills/autopilot/SKILL.md` as `gate-check`/`gate-answer`
      protocol blocks; fix the VALIDATE outcome vocabulary in §6 — **M**
      **Design decisions**: D3, D9
      **Dependencies**: 4.1

- [x] 4.3 Replace the "Deferred: automated re-decomposition" section of
      `skills/autopilot-roadmap/SKILL.md` with the replan protocol; document `--replan` in
      `skills/plan-roadmap/SKILL.md` — **S**
      **Spec scenarios**: ro *Replan gate proceeds and emits a request*
      **Design decisions**: D8, D9
      **Dependencies**: 4.1

- [x] 4.4 Run `install.sh` to resync `.claude/skills/` and `.agents/skills/` — **XS**
      **Design decisions**: D9
      **Dependencies**: 4.2, 4.3

- [x] Checkpoint: `test_prose_free_gates.py` green, review the diff, confirm only the three
      SKILL.md files and their mirrors changed

## Phase 5 — wp-integration

- [x] 5.1 Run the full skills suite (`skills/tests`, `skills/autopilot/scripts/tests`,
      `skills/shared/tests`) and `ruff check` on the touched packages — **S**
      **Dependencies**: all Phase 1–4 tasks

- [x] 5.2 `openspec validate encode-autopilot-gates-and-goal-gate-in-code --strict`; confirm
      every SHALL scenario above maps to at least one test task — **XS**
      **Dependencies**: 5.1

- [x] 5.3 Append the Implementation `PhaseRecord` via `write_both()`; update this file's
      checkboxes; commit and push — **XS**
      **Dependencies**: 5.2
