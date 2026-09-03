# Design: route-supervise-gates-through-the-approval-gate-service

## Context

After ri-06 (always-on roadmap) the autopilot loop has exactly one `gates.evaluate(Gate.X, …)`
call site per gate, records every decision in `loop-state.json` `gate_decisions`, parks a
`posture_block` as a `GateRequest` in `pending_gate`, and lets an operator answer it with
`runner.py gate-answer`, which builds a console `ApprovalDecision` in the same shape a
coordinator decision has. The roadmap orchestrator evaluates `replan_required` the same way
and writes to the `checkpoint.json` `gate_decisions` sidecar (`CheckpointManager.record_gate_decision`).

The supervise skill (ri-03) sits above both and has three decision points that never reach
`ApprovalGate`:

| Decision point | Today | Location |
|---|---|---|
| `cycle` roadmap approval ("Why the gate sits here") | chat "yes"; no gate id, deadline, or record | `skills/supervise/SKILL.md` §5 |
| `execute` precondition (durable roadmap-altitude approval) | prose + `test_workflow_contract.py`; `ExecutionAdapter.prepare` checks nothing | `execution.py:459-511` |
| Parked child resume | caller-invented `approval_ref` (1–256 chars, no provenance) | `execution.py:814-852`, schema `delegated-dispatch-attempt.schema.json` |

Constraints: `TRUST_POSTURE.md` is absent in this repo (all gates `block`); `cycle_state.py`
duplicates the gate/disposition enums as string literals; `skills/tests/supervise` runs as its
own pytest process (excluded from `testpaths`); `add-supervisor-candidate-work-digest`
(unstarted) also edits `cycle_state.py` and `SKILL.md`.

## Goals / Non-Goals

**Goals**
- Every supervise decision point is a `Gate` evaluated through `ApprovalGate.evaluate`.
- Every evaluation leaves a durable, correlated gate-decision record readable from tracked state.
- Every `approval_ref` used to prepare or resume delegated work resolves to such a record.
- Absent `TRUST_POSTURE.md` behaves exactly as today (human answers in-conversation).

**Non-Goals**
- Intake sizing/slotting judgment and the unchanged-fingerprint `--force` guard are not
  approval gates and stay as they are.
- Quarantine remains non-resumable by design (ri-03).
- No coordinator-side query API for `approval_gate_decision` memory events; the durable log
  is local tracked state, coordinator memory stays best-effort.
- No change to autopilot's seven call sites or to `replan_required`.

## Decisions

### D1 — A ninth gate, `roadmap_approval`, not a reuse of `proposal_approval`
Roadmap approval authorizes a DAG of items; proposal approval authorizes one change. The
operator must be able to set them independently (delegate per-change approval, keep roadmap
approval human, or the reverse). Adding `Gate.ROADMAP_APPROVAL = "roadmap_approval"` costs
nine mechanical edits (enum, template, `trust-posture.schema.json`,
`gate-decision.schema.json`, `supervisor-record.schema.json` `$defs.gate`, mirror schema if it
embeds the enum, `cycle_state._GATES` → import, two "eight gates" tests, spec text). Absent or
omitted entry → `block`, preserving fail-closed semantics.

### D2 — One router module is the only supervise path to `ApprovalGate`
`skills/supervise/scripts/gate_router.py` exposes:
- `evaluate(gate, context, *, workspace, repo_root, evaluator=None, now=None) -> RoutedDecision`
  — calls `ApprovalGate.evaluate` (default `build_default_gate(agent_id="supervise", repo_root=…)`),
  builds a gate-decision record via `build_gate_decision_record(decision, phase="SUPERVISE", extra=…)`
  with `decision_id` (uuid4), `source: "supervise"`, `roadmap_id`, optional `change_id` /
  `dispatch_id` / `item_id`, and appends it with `CheckpointManager.record_gate_decision`.
- `answer(gate, *, workspace, approved, note, context) -> RoutedDecision` — console answer using
  the shared `approval_gate.console_decision` helper (extracted from `runner._console_decision`,
  runner delegates to it; same record shape, design D4 of ri-06).
- `resolve_parked(attempt, *, workspace, repo_root, adapter, evaluator=None, now=None) -> ParkedResolution`.
- `require_approval_ref(checkpoint, approval_ref, *, gate, dispatch_id=None, roadmap_id=None) -> record`
  — raises `ApprovalRefError` unless the reference resolves.
- `gate_log(workspace, repo_root) -> list[record]` — sidecar ∪ active changes' `loop-state.json` `gate_decisions`.
A test asserts by AST that `ApprovalGate`, `build_default_gate`, and `.evaluate(` appear in no
supervise script other than `gate_router.py`.

### D3 — `approval_ref` is `gate-decision:<decision_id>` and must resolve
`ExecutionAdapter.resume(...)` calls `require_approval_ref(checkpoint, ref, gate=<parked gate or
escalate_resume>, dispatch_id=…)`; the record must have `outcome == "proceed"`. `prepare(...)`
gains a required keyword `roadmap_approval_ref` checked against a `roadmap_approval` record for
`checkpoint.roadmap_id`. The `continuation.approval_ref` schema gains `pattern:
"^gate-decision:[0-9a-f-]{36}$"`. Test fixtures get `approve_roadmap(workspace)` /
`approve_parked(workspace, attempt)` helpers that record console decisions.

### D4 — Parked-child resolution checks the prior coordinator approval before re-filing
For a `pending_gate` attempt, the child's `loop-state.json` `pending_gate` snapshot carries the
gate and, under `notify_with_timeout`, the coordinator `approval_id` it filed. `resolve_parked`:
1. maps `policy_pause` → `Gate.ESCALATE_RESUME` (the child is in `ESCALATE` by contract) and
   `pending_gate` → `Gate(parked.gate)`; an unknown gate name is a schema error, not a decision;
2. if the snapshot has an `approval_id`, calls `coordinator.check_approval(approval_id)` first —
   `approved` → `PROCEED/approved`, `denied` → `BLOCKED/rejected`, `pending` → re-surface without
   re-filing (returns the existing deadline);
3. otherwise calls `evaluate(...)` against the current posture (hot reload: an operator who flips
   the gate to `auto` between cycles unparks it on the next cycle without a console answer);
4. `PROCEED` → `adapter.resume(workspace, dispatch_id=…, approval_ref=…, kind=…)`;
   `BLOCKED` → returns a `pending_gates` entry `{gate, change_id, requested_at, deadline,
   disposition, approval_id, decision_id, source: "supervise"}`.
`deadline` for `block` is `requested_at + DEFAULT_BLOCK_HORIZON` (7 days) — the record schema
requires a deadline and a blocked gate has none of its own.

### D5 — `cycle` gate protocol replaces the prose stop
`cycle_state.py gate-check --roadmap <id> [--context K=V…]` evaluates `roadmap_approval` with
`{roadmap_id, item_count, fingerprint}`. Exit codes mirror `runner.py gate-check`: 3 = proceed
(SKILL continues into `/plan-roadmap` approval and `execute`), 0 = parked (prints the pending
entry; SKILL renders it under "Needs a decision" and stops), 4 = blocked/other. `gate-answer
--roadmap <id> --gate roadmap_approval --decision approved|rejected [--note]` records the console
decision. A `proceed` decision is also mirrored into the supervisor record's `standing_decisions`
(`id = decision_id`, `scope = roadmap_id`, `decision = "roadmap_approval:proceed"`) so a
rehydrated session sees it. `/autopilot-roadmap` direct invocation runs `gate-answer … --decision
approved --note "direct invocation"` before `execute` — the operator's command is the approval,
and the record makes it durable.

### D6 — The evaluation log is tracked state; coordinator memory is best-effort
`gate-log` reads `checkpoint.json` `gate_decisions` plus each active change's `loop-state.json`
`gate_decisions` and prints one JSON array sorted by `recorded_at`. `BridgeAuditSink` remains the
remote path (unchanged, never raises). Acceptance outcome 2 is verified against `gate-log`.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Prose-free gates: 0 `Gate` names in `skills/supervise/SKILL.md` outside protocol blocks | `skills/tests/supervise/test_prose_free_gates.py` (mirrors `skills/tests/autopilot/test_prose_free_gates.py`) | new |
| Decision provenance: 0 unresolvable `approval_ref` accepted | `test_execution.py::test_resume_rejects_unresolvable_ref`, `test_prepare_refuses_without_roadmap_approval`, `test_gate_router.py::test_require_approval_ref_*` | new |
| Evaluation completeness: 0 evaluations without a record in a full simulated run | `test_gate_router_e2e.py` (fake coordinator + in-memory evaluator; asserts `gate-log` covers every evaluate call and every `approval_ref`) | new |
| Hot reload: posture edits reflected at next evaluation | `test_gate_router.py::test_parked_child_unparks_after_posture_flip` | new |
| Compatibility: absent posture identical to today | `shared/tests/test_trust_posture.py` (nine gates all block), `test_execution.py` parked/resume paths with console answers | existing + updated |
| Host-assisted: 0 LLM SDK imports under `skills/supervise/scripts/` | existing invariant test extended to `gate_router.py` | existing |
| Router is the single seam | `test_gate_router.py::test_only_gate_router_imports_approval_gate` (AST scan) | new |

## Alternatives Considered

- **Resume-seam only** (proposal Approach 1): rejected — leaves the roadmap-altitude gate as
  prose and cannot give `auto`/console decisions a reference.
- **Reuse `proposal_approval` at roadmap altitude** (Approach 3): rejected — conflates two
  decisions the operator must set independently.
- **Hash-derived `approval_ref`** (sha256 of the canonical record instead of a stored
  `decision_id`): rejected — clever but opaque to operators reading `checkpoint.json`;
  `gate-decision.schema.json` already allows additional properties so a stored id is free.
- **Enforce roadmap approval only in the SKILL step, not in `prepare`**: rejected — that is
  prose again; `prepare` is the last deterministic point before dispatch.
- **Have the supervisor shell out to `runner.py gate-check` inside each child worktree**:
  rejected — the roadmap-approval gate has no change to run it in, and the supervisor would
  still need its own ledger for the `approval_ref`.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `prepare` signature change churns `test_execution.py` (1,259 lines) | One `approve_roadmap(workspace)` fixture; grep-driven update; contract test pins the new signature |
| Nine-gate growth breaks "eight" assertions in `shared/tests`, autopilot tests, spec text | All sites enumerated in tasks 1.x; `test_gate_call_sites` unaffected (it iterates autopilot's seven and asserts `replan_required` is not autopilot's — `roadmap_approval` is added to that non-autopilot set) |
| Re-evaluating a `notify_with_timeout` gate every cycle spams approvals | D4 step 2 checks the filed `approval_id` first and never re-files while it is pending |
| `add-supervisor-candidate-work-digest` conflicts in `cycle_state.py` / `SKILL.md` | It is unstarted; note in its proposal to rebase; keep this change's `cycle_state.py` edits to enum imports + three new subcommands |
| Coordinator unreachable during `notify_with_timeout` | Unchanged `ApprovalGate` semantics: `coordinator_unreachable` → BLOCKED, recorded, surfaced |
| `BridgeCoordinatorClient.push_notification` always returns `False` (diagnostic endpoint) so `default_action: proceed` fails closed | Pre-existing ri-05 behaviour; documented in the SKILL, not changed here |

## Migration Plan

1. Land contracts first (enum, template, schemas, tests) — additive, no behaviour change.
2. Land the router, `execution.py` checks, and `cycle_state.py` subcommands with tests.
3. Land `SKILL.md` edits and the prose-free test; run `install.sh` to resync runtime mirrors.
4. Rollback: revert the change; persisted `gate_decisions` records with extra fields remain
   schema-valid; a `TRUST_POSTURE.md` carrying `roadmap_approval` would fail validation against
   the old schema, so the rollback note tells operators to drop that key.
