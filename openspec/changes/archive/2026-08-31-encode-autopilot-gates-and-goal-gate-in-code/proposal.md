# Encode autopilot gates and goal gate in code

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `encode-autopilot-gates-and-goal-gate-in-code`
> Roadmap item: `ri-06`
> Effort: L
> Priority: 1

## Why

`skills/autopilot/scripts/autopilot.py` runs the phase loop to terminal states,
but every human gate lives only as prose in `skills/autopilot/SKILL.md`:

- Proposal approval — `SKILL.md:229` "Wait for proposal approval before
  continuing"; `_phase_plan` transitions straight to PLAN_ITERATE.
- Merge handoff — `SKILL.md:687` "STOP — Await human approval for merge";
  `TRANSITIONS["SUBMIT_PR"] == {"created": "DONE"}` is unconditional and
  `_phase_submit_pr` returns the literal `"created"` when no callback is injected.
- ESCALATE resume — `SKILL.md:66-70` "Ask if the issue has been resolved";
  `check_escalation_resolved()` returns `False` whenever no `gate_check_fn` is
  injected, which is always.
- `replan_required` — `autopilot-roadmap/SKILL.md:163` "autopilot does not act
  on it today"; `checkpoint.fail_item` only ever sets `BLOCKED`, and
  `/plan-roadmap` has no replan mode.

Nothing guards DONE: a run resumed with a hand-edited `current_phase: SUBMIT_PR`
reaches DONE with no VALIDATE record at all. Validation success is sequentially
prior, never structurally required.

Meanwhile the policy machinery this change needs already shipped and has zero
consumers: `skills/shared/trust_posture.py` (`Gate` enum, eight members that map
1:1 onto the prose gates; absent `TRUST_POSTURE.md` ⇒ every gate `block`) and
`skills/shared/approval_gate.py` (`ApprovalGate.evaluate()` → `ApprovalDecision`
with `auto` / `notify_with_timeout` / `block` dispositions, fail-closed on
coordinator-unreachable). ri-05's learning log states the contract directly:
"ri-06 calls `ApprovalGate.evaluate()` at real autopilot gate sites and persists
loop state on BLOCKED."

Prose gates are invisible to unattended loops (`docs/decisions/agent-archetypes.md:45`);
this is the primary blocker to the dispatcher daemon (ri-08) and to supervisor
roadmap ri-04, which carries `external_depends_on: always-on:ri-06`.

## What Changes

1. **Gate call sites in `autopilot.py`.** Every `Gate` member gets exactly one
   call site, evaluated through an injected `GateEvaluator` seam (default:
   `approval_gate.build_default_gate`):

   | Gate | Call site (phase → edge) | On PROCEED | On BLOCKED |
   |---|---|---|---|
   | `gatekeeper_escalation` | GATEKEEPER verdict `escalate` | enter ESCALATE as today | same (block only records) |
   | `proposal_approval` | PLAN → PLAN_ITERATE | advance | gate pending |
   | `plan_review_convergence_failure` | PLAN_REVIEW `max_iter` / PLAN_FIX `stuck` | enter ESCALATE | gate pending |
   | `validation_failure` | VALIDATE `failed` / VAL_FIX `stuck` | VAL_FIX / ESCALATE as today | gate pending |
   | `escalate_resume` | ESCALATE → `_previous_phase` | resume | stay parked |
   | `replan_required` | autopilot-roadmap item status `replan_required` | emit replan request | item stays `replan_required` |
   | `pr_creation` | SUBMIT_PR before `gh pr create` | create PR | gate pending |
   | `merge` | SUBMIT_PR → DONE | record merge authorization in loop state + handoff | gate pending |

   `merge` PROCEED **records authorization only**; DONE still hands off to
   `/cleanup-feature`. Autopilot does not merge (ri-12 owns headless merge).

2. **Console interviewer via `runner.py`.** A BLOCKED decision whose resolution is
   `posture_block` in a host-assisted session does not exit the loop. The loop
   returns a structured `gate_pending` outcome; `runner.py` gains
   `gate-check <change-id>` (prints the pending `GateRequest` JSON: gate, context,
   prompt text) and `gate-answer <change-id> --gate <name> --decision approved|rejected`
   (records an `ApprovalDecision` with resolution `console_approved` /
   `console_rejected` into `LoopState.gate_decisions` and re-runs the transition).
   The loop cannot advance past a gate without a recorded decision, so enforcement
   is in code while the *asking* stays host-executed (host-assisted invariant).
   `notify_with_timeout` and `coordinator_unreachable` resolutions park the loop
   exactly as ESCALATE does today (save state, exit).

3. **Goal gate at DONE.** A new `skills/autopilot/scripts/goal_gate.py` exposes
   `check_goal_gate(state, change_dir) -> GoalGateVerdict`. It refuses DONE unless
   **both** hold: (a) `gate_logic.check_phase_status()` over
   `openspec/changes/<id>/validation-report.md` reports `pass` for the required
   phases (and VAL_REVIEW converged when `val_review_enabled`), and (b)
   `LoopState.phase_history` contains a `{"phase": "VALIDATE", "outcome": "passed"}`
   entry recorded after the report's `git` timestamp. `transition()` consults it
   on every edge into DONE except `ESCALATE → abandoned`, which records
   `goal_gate: abandoned` instead of `passed`.

4. **`replan_required` producer and consumer.** `CheckpointManager.fail_item`
   accepts `replan: bool`; when the failing item's outcome payload carries
   `replan: true` the dependents become `replan_required` instead of `blocked`.
   The autopilot-roadmap orchestrator evaluates `Gate.REPLAN_REQUIRED` for each
   such item and, on PROCEED, emits a `ReplanRequest` the host executes via a new
   `/plan-roadmap --replan <roadmap-id>` mode (re-decompose the affected subgraph,
   preserving completed items and their learning-log entries).

5. **SKILL.md de-prosed.** Every gate section in `skills/autopilot/SKILL.md` and
   the deferred-replan section in `skills/autopilot-roadmap/SKILL.md` is replaced
   by the `runner.py gate-check` / `gate-answer` protocol. The VALIDATE outcome
   vocabulary mismatch (`continue`/`escalate` in prose vs `passed`/`failed` in
   `TRANSITIONS`) is fixed in the same edit. Mirrors resynced via `install.sh`.

6. **Loop state schema v5.** `LoopState` gains `gate_decisions: list[dict]`
   (audit records from `ApprovalDecision.to_audit_record()`) and
   `goal_gate: dict | None`; v4 state migrates with empty defaults.

## Approaches Considered

### Approach 1: Thin call sites + host console interviewer (Recommended)

Evaluate each `Gate` at its natural site inside the existing `_phase_*` handlers
and `transition()`; surface blocked-in-interactive as a `gate_pending` outcome
that `runner.py` exposes for the host to ask and answer.

- **Pros**
  - Uses ri-04/ri-05 exactly as designed; ~8 thin call sites, no new phases.
  - Preserves `_PHASE_TASKS` 13-phase coverage invariant and the
    fix-compact-hook assumption that `apply-outcome` fires at phase boundaries.
  - Interactive default parks nowhere new — the ask moves from prose to a
    runner protocol, behaviour is byte-identical for an interactive operator.
  - Orchestrator stays the only actor that mutates `current_phase`
    (fix-autopilot-archetype V2 constraint).
- **Cons**
  - Gate context (proposal path, PR URL) has to be threaded into each handler.
  - Two new runner subcommands and a `GateRequest` JSON contract to test.
- **Effort**: L

### Approach 2: Gates as explicit state-machine phases

Insert `PROPOSAL_GATE`, `PR_GATE`, `MERGE_GATE`, `RESUME_GATE` phases into
`TRANSITIONS`, each with its own `_phase_*` handler and `phase_history` entry.

- **Pros**
  - Gates become first-class in status output and handoff boundaries.
  - Uniform: every gate is a phase with the same dispatch shape.
- **Cons**
  - Grows the phase set from 15 to 19; breaks `test_phase_tasks.py`'s
    all-phases-covered invariant and the SKILL.md "14 non-terminal phases" text.
  - Shifts `_HANDOFF_BOUNDARIES`, colliding with
    `fix-compact-hook-phase-boundary-detection`'s `last_handoff_id` timing.
  - `replan_required` and ESCALATE resume don't fit a phase model.
- **Effort**: L

### Approach 3: Central transition guard

A single `(from_phase, to_phase) → Gate` map evaluated inside `_apply_transition`;
no per-handler edits.

- **Pros**
  - One place to read the whole gate policy; smallest diff to handlers.
- **Cons**
  - Context isn't available at transition time (the PR URL is produced inside
    `_phase_submit_pr`; the proposal path inside `_phase_plan`).
  - `escalate_resume`, `replan_required`, and the GATEKEEPER verdict aren't
    edges, so three of eight gates need a side channel anyway.
  - Hides gate evaluation from the phase handler that has to render the ask.
- **Effort**: M

### Recommendation

Approach 1. Approach 3's smaller diff is illusory — three gates fall outside the
edge model and the two that matter most (proposal, merge) need handler-local
context. Approach 2 buys uniformity at the cost of two in-flight changes'
invariants. Approach 1 lands as what ri-05 already promised: call sites.

### Selected Approach

**Approach 1 — Thin call sites + host console interviewer** (Gate 1, 2026-08-28).
Discovery decisions carried into the design: (a) blocked-in-interactive is a
console ask through `runner.py`, never a silent park; (b) goal-gate evidence is
`validation-report.md` **and** `phase_history`; (c) all eight `Gate` members get
a call site; (d) `replan_required` gets an explicit-signal producer plus the
consumer path. No modifications requested.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Compatibility | Interactive behaviour with no `TRUST_POSTURE.md` | Identical park points to today (proposal, merge, escalate), verified by the existing happy-path tests plus new gate tests | VALIDATE (unit) |
| Operability | Unattended run under an all-`auto` posture | Reaches SUBMIT_PR with zero `gate_pending` outcomes | VALIDATE (e2e test) |
| Auditability | Gate decisions persisted | 100% of decisions (incl. auto and console) present in `LoopState.gate_decisions` and coordinator memory `approval_gate_decision` | VALIDATE (unit) |
| Resilience | Coordinator unreachable during `notify_with_timeout` | Loop parks with resolution `coordinator_unreachable`; never proceeds | VALIDATE (unit) |
| Correctness | DONE without VALIDATE pass | 0 paths; property test over hand-edited `current_phase` values | VALIDATE (unit) |

## Impact

- `skills/autopilot/scripts/{autopilot.py, runner.py, phase_agent.py, handoff_builder.py}`, new `goal_gate.py`
- `skills/autopilot/SKILL.md`, `skills/autopilot-roadmap/SKILL.md`, `skills/plan-roadmap/SKILL.md`
- `skills/roadmap-runtime/scripts/checkpoint.py`, `skills/autopilot-roadmap/scripts/orchestrator.py`
- `skills/plan-roadmap/scripts/` (replan entry point)
- Specs: `skill-workflow` (ADDED gate + goal-gate requirements), `roadmap-orchestration` (MODIFIED adaptive execution)
- Tests under `skills/autopilot/scripts/tests/`, `skills/tests/autopilot/`, `skills/tests/roadmap-runtime/`, `skills/tests/plan-roadmap/`

## Out of Scope

- Performing the merge inside autopilot (ri-12 headless merge-pull-requests).
- Heuristic hard-vs-workaroundable classification in `fail_item` (explicit
  `replan: true` signal only).
- Instantiating a repo `TRUST_POSTURE.md` (operator decision; template stays).
- Routing supervise gates (supervisor roadmap ri-04, downstream of this change).

## Dependencies

- `ri-01` fix-autopilot-archetype-and-apply-outcome — completed
- `ri-02` fix-compact-hook-phase-boundary-detection — completed
- `ri-05` build-approval-gate-service-interviewer-abstraction — completed

## Acceptance Outcomes

- Grep of skills/autopilot/SKILL.md finds no gate whose only enforcement is prose.
- An unattended run with an auto-everything posture reaches SUBMIT_PR without interaction; with the default posture it parks exactly where it does today.
- A run whose VALIDATE record is missing or failed cannot reach DONE.
- replan_required re-invokes /plan-roadmap in replan mode when the posture allows.
