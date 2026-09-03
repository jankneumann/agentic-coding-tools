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
(unstarted) rewrites `cycle` §2–§5 of `SKILL.md` but explicitly leaves `cycle_state.py`'s
surface unchanged. Two facts about the gate service shape everything below:

- `ApprovalGate.evaluate` is **synchronous**. Under `notify_with_timeout` it files the
  approval, pushes the notification, polls `check_approval` until the posture's
  `timeout_seconds` elapse, then applies `default_action`. It never returns "pending"; every
  decision it returns is terminal (`auto`, `approved`, `rejected`, `timeout_default_*`,
  `posture_block`, `coordinator_unreachable`).
- The child's `pending_gate` snapshot (`build_gate_request` in `autopilot.py`) is built
  **only for `posture_block`** and carries `{gate, phase, requested_at, prompt, context,
  posture}` — never an `approval_id`. A child that timed out under `notify_with_timeout`
  enters ESCALATE, so it reaches the supervisor as `policy_pause`, not `pending_gate`.

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
approval human, or the reverse). Adding `Gate.ROADMAP_APPROVAL = "roadmap_approval"` is
mechanical but touches every place that spells the enum out: the enum and its docstring,
`TRUST_POSTURE.template.md`, five schema files (`trust-posture.schema.json` `gates`,
`gate-decision.schema.json` `gate`, `gate-request.schema.json` `gate`,
`supervisor-record.schema.json` `$defs.gate`, `supervisor-record-mirror.schema.json`
`$defs.gate` — the mirror does embed the enum literally), `cycle_state._GATES` → import, the
two "eight gates" tests in `shared/tests/test_trust_posture.py`, `test_gate_schemas.py`
(which pins `gate-request` and `gate-decision` to `Gate`), `test_gate_call_sites.py` (which
must list `roadmap_approval` next to `replan_required` as a non-autopilot gate), and spec
text. Absent or omitted entry → `block`, preserving fail-closed semantics.

### D2 — One router module is the only supervise path to `ApprovalGate`
`skills/supervise/scripts/gate_router.py` exposes:
- `evaluate(gate, context, *, workspace, repo_root, evaluator=None, now=None) -> RoutedDecision`
  — applies the prior-record rule (D4 step 0), then calls `ApprovalGate.evaluate` (default
  `build_default_gate(agent_id="supervise", repo_root=…)`), builds a gate-decision record via
  `shared.approval_gate.build_gate_decision_record(decision, phase="SUPERVISE", extra=…)` with
  `decision_id` (uuid4), `source: "supervise"`, `verb` (`cycle` / `execute` / `resume`),
  `roadmap_id`, optional `change_id` / `dispatch_id` / `item_id`, and appends it with
  `CheckpointManager.record_gate_decision`. The record builder is **moved** from
  `autopilot.py` into `shared.approval_gate` (autopilot keeps a delegating alias so its call
  sites and `test_gate_call_sites` are untouched); supervise must not import `autopilot.py`.
  The roadmap orchestrator's private `_gate_decision_record` already emits the same shape
  and is left alone (out of scope).
- `answer(gate, *, workspace, approved, note, context) -> RoutedDecision` — console answer using
  the shared `approval_gate.console_decision(gate, posture, approved, note)` helper (extracted
  from `runner._console_decision`; `posture` is the `{disposition, posture_present}` snapshot
  a parked record carries, or — for an originating `roadmap_approval` answer, D5 — the
  snapshot the router takes from the live posture). The runner delegates to it; same record
  shape, design D4 of ri-06.
- `resolve_parked(attempt, *, workspace, repo_root, adapter, evaluator=None, now=None) -> ParkedResolution`.
- `require_approval_ref(checkpoint, approval_ref, *, gate, dispatch_id=None, roadmap_id=None) -> record`
  — raises `ApprovalRefError` unless the reference resolves.
- `gate_log(workspace, repo_root) -> list[record]` — sidecar ∪ the roadmap's changes'
  `loop-state.json` `gate_decisions` (D6).
A test asserts by AST that `ApprovalGate`, `build_default_gate`, `check_filed`, and
`.evaluate(` appear in no supervise script other than `gate_router.py`.

### D3 — `approval_ref` is `gate-decision:<decision_id>` and must resolve
`ExecutionAdapter.resume(...)` calls `require_approval_ref(checkpoint, ref, gate=<parked gate or
escalate_resume>, dispatch_id=…)`; the record must have `outcome == "proceed"`. `prepare(...)`
gains a required keyword `roadmap_approval_ref` checked against a `roadmap_approval` record for
`checkpoint.roadmap_id`. The `continuation.approval_ref` schema gains the uuid4 pattern in
`contracts/schemas/delegated-dispatch-attempt.continuation.patch.json` (`^gate-decision:` +
8-4-4-4-12 hex); the same pattern is applied to the echo in
`supervised-dispatch-request.schema.json`. Provenance is checked against the **tracked**
ledger: whoever can write `checkpoint.json` can forge a record, which is exactly the trust
boundary `TRUST_POSTURE.md` itself sits on (repository write access), so no signing is
added. Test fixtures get `approve_roadmap(workspace)` / `approve_parked(workspace, attempt)`
helpers that record console decisions.

### D4 — Every router evaluation applies a prior-record rule; parked children are re-evaluated against the current posture

Because `evaluate` is synchronous and the child's `pending_gate` snapshot never carries an
`approval_id` (Context), "check the filed approval before re-filing" cannot be a property of the
child snapshot. It is instead a rule the router applies to **its own ledger** before every
evaluation, keyed by the decision's subject:

- subject key = `(gate, roadmap_id, dispatch_id)` for parked attempts and
  `(gate, roadmap_id, roadmap_fingerprint)` for `roadmap_approval` (D5).

**Step 0 — prior-record rule.** Look up the latest sidecar record for the subject key.
1. `outcome == proceed` → reuse it: return its `decision_id`, record nothing, evaluate nothing.
2. `outcome == blocked`, `resolution == posture_block` → the console question is still open.
   Re-evaluate only if the posture's disposition for the gate differs from the record's
   `disposition` (hot reload: a flip to `auto` unparks, a flip to `notify_with_timeout` files);
   otherwise re-surface the existing `pending_gates` entry (same `decision_id`, same
   `deadline`) without recording a second `posture_block`.
3. `outcome == blocked`, `approval_id` set (`timeout_default_block`, `coordinator_unreachable`
   after filing) → call `ApprovalGate.check_filed(gate, approval_id)` first. It wraps the
   gate service's own `_interpret_status`: `approved` → `PROCEED/approved`, `denied` →
   `BLOCKED/rejected`, `expired` → the default action, `pending` → `None`. A non-`None`
   decision is recorded and acted on — a human who answered in the coordinator after the
   local timeout is honoured, and nothing is re-filed. `None` (still pending server-side)
   re-surfaces the existing entry and deadline. Only after the prior approval is terminal
   does the router fall through to step 1 and file anew — so re-notification is bounded to
   one request per expired approval per operator-run cycle, never one per poll.
4. `outcome == blocked`, `resolution in {rejected, console_rejected}` → terminal for the
   subject. Re-surface it; do not re-evaluate until the subject key changes (a new DAG
   fingerprint, a new dispatch) or the operator answers with `gate-answer`.

**Step 1 — `resolve_parked(attempt, …)`** for a parked attempt:
1. maps `policy_pause` → `Gate.ESCALATE_RESUME` (the child is in `ESCALATE` by contract) and
   `pending_gate` → `Gate(parked.gate)`; an unknown gate name is a schema error, not a decision;
2. applies step 0 with `dispatch_id` as the subject;
3. otherwise calls `evaluate(...)` against the current posture (hot reload: an operator who flips
   the gate to `auto` between cycles unparks it on the next cycle without a console answer; a
   `notify_with_timeout` posture files and waits inside `evaluate`, bounded by `timeout_seconds`);
4. `PROCEED` → `adapter.resume(workspace, dispatch_id=…, approval_ref=…, kind=…)`;
   `BLOCKED` → returns a `pending_gates` entry `{gate, change_id, requested_at, deadline,
   disposition, approval_id, decision_id, source: "supervise"}` whose `deadline` is
   `requested_at + timeout_seconds` when an approval was filed and
   `requested_at + DEFAULT_BLOCK_HORIZON` (7 days) otherwise — the record schema requires a
   deadline and a blocked gate has none of its own.

### D5 — `cycle` gate protocol replaces the prose stop
`cycle_state.py gate-check --roadmap <id> [--context K=V…]` evaluates `roadmap_approval` with
`{roadmap_id, item_count, roadmap_fingerprint}`, where `roadmap_fingerprint` is the sha256 of
the roadmap's sorted `(item_id, change_id, sorted(depends_on))` tuples — the DAG's structure,
not its progress — so an approved roadmap is asked once and re-asked only when `refine-roadmap`
or a replan changes the DAG (this answers the plan-phase open question: a `proceed` decision
has no time expiry, `standing_decisions.expires_at` stays `null`, and expiry is structural).
Exit codes mirror `runner.py gate-check`: 3 = proceed (SKILL continues into `/plan-roadmap`
approval and `execute`; a reused decision also exits 3 and prints the reused record), 0 =
parked on `posture_block` (prints the pending entry; SKILL renders it under "Needs a decision"
and stops), 4 = blocked terminally (`rejected`, `timeout_default_block`,
`coordinator_unreachable`; the entry is printed with its resolution and the SKILL stops — the
operator may still answer it with `gate-answer`, since a human answer satisfies every
disposition). Under `notify_with_timeout` a `gate-check` waits up to the posture's
`timeout_seconds`; the SKILL's protocol block says so.

`gate-answer --roadmap <id> --gate <gate> --decision approved|rejected [--note] [--dispatch-id]`
records the console decision. For every gate except `roadmap_approval` it requires a prior
parked record for the subject (mirrors `runner.py gate-answer`: answering a question nobody
asked is a host bug and is refused without recording). `roadmap_approval` is the one gate whose
answer may **originate** a record — the operator running `/autopilot-roadmap` directly, or
saying "yes" in `/supervise cycle` before `gate-check` ran — because the operator's command
is the human answer; its `posture` snapshot is taken from the live posture. A `proceed`
decision is also mirrored into the supervisor record's `standing_decisions` (`id =
decision_id`, `scope = roadmap_id`, `decision = "roadmap_approval:proceed"`, `rationale` =
the note) so a rehydrated session sees it, and the printed `roadmap_approval_ref`
(`gate-decision:<decision_id>`) is what `execute` passes to `prepare`. `/autopilot-roadmap`
direct invocation runs `gate-answer --roadmap <id> --gate roadmap_approval --decision approved
--note "direct invocation"` before `execute`.

### D6 — The evaluation log is tracked state; coordinator memory is best-effort
`gate-log --roadmap <id>` reads the workspace's `checkpoint.json` `gate_decisions` plus the
`gate_decisions` of `openspec/changes/<change_id>/loop-state.json` for every `change_id` named
by that roadmap's items (not every change under `openspec/changes/`), and prints one JSON array
sorted by `recorded_at`, each record tagged with its `origin` (`checkpoint` or the change id).
`BridgeAuditSink` remains the remote path (unchanged, never raises). Acceptance outcome 2 is
verified against `gate-log`.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Prose-free gates: 0 `Gate` names in `skills/supervise/SKILL.md` outside protocol blocks | `skills/tests/supervise/test_prose_free_gates.py` (mirrors `skills/tests/autopilot/test_prose_free_gates.py`) | new |
| Decision provenance: 0 unresolvable `approval_ref` accepted | `test_execution.py::test_resume_rejects_unresolvable_ref`, `test_prepare_refuses_without_roadmap_approval`, `test_gate_router.py::test_require_approval_ref_*` | new |
| Evaluation completeness: 0 evaluations without a record in a full simulated run | `test_gate_router_e2e.py` (fake coordinator + in-memory evaluator; asserts `gate-log` covers every evaluate call and every `approval_ref`) | new |
| Hot reload: posture edits reflected at next evaluation | `test_gate_router.py::test_parked_child_unparks_after_posture_flip` | new |
| Ask once: an approved roadmap is not re-asked until its DAG changes | `test_gate_router.py::test_roadmap_approval_reused_until_fingerprint_changes` | new |
| Late answer honoured, nothing re-filed: a coordinator approval answered after the local timeout resolves on the next cycle without a second request | `test_gate_router.py::test_check_filed_before_refiling`, `shared/tests/test_approval_gate.py::test_check_filed_*` | new |
| Originating console answer is limited to `roadmap_approval` | `test_cycle_state.py::test_gate_answer_refuses_unparked_gate` | new |
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
- **An asynchronous notify path in the router (file the approval, return "pending", poll
  on later cycles)**: rejected — it would re-implement `ApprovalGate._notify` outside
  `approval_gate.py` (timeout, default action, undelivered-notification fail-closed), which
  is the bypass acceptance outcome 3 forbids. The router keeps the synchronous `evaluate`
  and adds only `check_filed`, a thin public wrapper over the gate service's own status
  interpretation, for the late-answer case.
- **Re-ask `roadmap_approval` on every cycle**: rejected — one notification per cycle for an
  already-approved roadmap is the interruption ri-04 exists to remove; the DAG fingerprint
  is the smallest key that still re-asks when the approved shape changes.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `prepare` signature change churns `test_execution.py` (1,259 lines) | One `approve_roadmap(workspace)` fixture; grep-driven update; contract test pins the new signature |
| Nine-gate growth breaks "eight" assertions in `shared/tests`, autopilot tests, spec text | All sites enumerated in tasks 1.x; `test_gate_call_sites` unaffected (it iterates autopilot's seven and asserts `replan_required` is not autopilot's — `roadmap_approval` is added to that non-autopilot set) |
| Re-evaluating a `notify_with_timeout` gate every cycle spams approvals | D4 step 2 checks the filed `approval_id` first and never re-files while it is pending |
| `add-supervisor-candidate-work-digest` rewrites `cycle` §2–§5 of `SKILL.md` (it does not touch `cycle_state.py`) | It is unstarted; task 3.4 leaves a rebase note naming the §5 protocol block; this change's `SKILL.md` edits stay inside §5, `### Approval gate`, and `### Reconcile and resume` |
| `test_workflow_contract.py` slices `SKILL.md` on `## Verb: \`execute\``, `### Approval gate`, `### Prepare and launch`, `### Reconcile and resume` and pins ``durable `approval_ref` `` | Task 3.2 keeps those headings and the phrase (the new prose says "a durable `approval_ref` of the form `gate-decision:<decision_id>`"); wp-skill-docs may edit the test if a pin must move |
| A forged `proceed` record in the tracked ledger would pass `require_approval_ref` | Same trust boundary as `TRUST_POSTURE.md` (repository write access); the ledger is reviewed in the PR like any tracked file; no signing (out of scope) |
| Re-notification under `notify_with_timeout` | Bounded by D4 step 0.3: one request per expired approval per operator-run cycle; a `pending` server status is never re-filed |
| Coordinator unreachable during `notify_with_timeout` | Unchanged `ApprovalGate` semantics: `coordinator_unreachable` → BLOCKED, recorded, surfaced |
| `BridgeCoordinatorClient.push_notification` always returns `False` (diagnostic endpoint) so `default_action: proceed` fails closed | Pre-existing ri-05 behaviour; documented in the SKILL, not changed here |

## Migration Plan

1. Land contracts first (enum, template, schemas, tests) — additive, no behaviour change.
2. Land the router, `execution.py` checks, and `cycle_state.py` subcommands with tests.
3. Land `SKILL.md` edits and the prose-free test; run `install.sh` to resync runtime mirrors.
4. Rollback: revert the change; persisted `gate_decisions` records with extra fields remain
   schema-valid; a `TRUST_POSTURE.md` carrying `roadmap_approval` would fail validation against
   the old schema, so the rollback note tells operators to drop that key.
