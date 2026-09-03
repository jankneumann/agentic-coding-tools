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
- Every evaluation leaves a durable, correlated gate-decision record: tracked, in the roadmap
  workspace's `checkpoint.json`, for the supervisor's own gates; readable through the
  attempt's recorded worktree for a child's (D6).
- Every `approval_ref` used to prepare or resume delegated work resolves to such a record.
- Absent `TRUST_POSTURE.md` behaves exactly as today (human answers in-conversation).

**Non-Goals**
- Intake sizing/slotting judgment and the unchanged-fingerprint `--force` guard are not
  approval gates and stay as they are.
- Quarantine remains non-resumable by design (ri-03).
- No coordinator-side query API for `approval_gate_decision` memory events; the durable log
  is durable local state, coordinator memory stays best-effort.
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
`$defs.gate` — the mirror does embed the enum literally), `cycle_state._GATES` → import
(task 2.0, which must land before the router's projection — see D7), the
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
  `decision_id` (uuid4), `source: "supervise"`, `verb` (`cycle` / `execute` / `resume` —
  declared as an optional property with that enum in the change's `gate-decision.schema.json`
  so implementers and tests cannot disagree about it),
  `roadmap_id`, optional `change_id` / `dispatch_id` / `item_id`. Every record the router
  writes for `gate=roadmap_approval` — whether from a fresh `evaluate`, a `check_filed` reuse
  of a filed approval (D4 step 0.3), or a console `answer` — additionally stamps
  `roadmap_fingerprint` (D5's sha256, so `require_approval_ref` can reject a stale reference —
  D3) at the single point where the router builds and appends the record, so no internal path
  can produce an unstamped `roadmap_approval` record; only `roadmap_approval` records carry
  one. Separately, this change adds an optional `notified: Optional[bool] = None` field to the existing
  `_Draft` / `ApprovalDecision` dataclasses in `shared.approval_gate` (ri-05's, unmodified
  otherwise) and threads `_notify`'s already-local `notified` value into every `_Draft` it
  builds via `_interpret_status` / `_apply_default`, so `to_audit_record()` exposes it and
  `build_gate_decision_record` copies it onto the ledger record with no separate stamping
  step. `BridgeCoordinatorClient.push_notification` always returns `False` in production
  today (ri-05), so every filed approval is recorded `notified: false` until that changes,
  which is exactly the fail-closed input `check_filed` needs (D4 step 3); a console-originated
  `roadmap_approval` answer has no coordinator delivery concept and records `notified: null`.
  The router appends it with
  `CheckpointManager.record_gate_decision`. `CheckpointManager.load()` raises
  `FileNotFoundError` when the workspace has no `checkpoint.json`, and nine of the ten
  workspaces under `openspec/roadmaps/` have none (only an executed roadmap does), so the
  router bootstraps exactly as `orchestrator.py` does — `manager.load() if manager.exists()
  else manager.create(roadmap)` — before its first record. Creating the checkpoint at the
  `cycle` gate is why `gate-check` never runs under `--dry-run` (D5). The record builder is **moved** from
  `autopilot.py` into `shared.approval_gate` (autopilot keeps a delegating alias so its call
  sites and `test_gate_call_sites` are untouched); supervise must not import `autopilot.py`.
  The roadmap orchestrator's private `_gate_decision_record` already emits the same shape
  and is left alone (out of scope).
- `answer(gate, *, workspace, approved, note, context) -> RoutedDecision` — console answer using
  the shared `approval_gate.console_decision(gate, posture, approved, note)` helper (extracted
  from `runner._console_decision`). `posture` is the `{disposition, posture_present}` snapshot
  of **the router's own prior blocked record** for that subject, not of the parked attempt:
  `supervised-dispatch-result.schema.json` caps `parked` at `{kind, reason, gate, deadline,
  resume_hint}` with `additionalProperties: false`, and `execution.py` re-checks that same
  key set, so a supervise-side parked attempt carries no posture at all. (The autopilot
  `pending_gate` in `loop-state.json` that `runner._console_decision` reads *does* carry one;
  that is the difference.) For an originating `roadmap_approval` answer (D5) the snapshot
  comes from the live posture, and — like every other `roadmap_approval` record the router
  writes — it stamps `roadmap_fingerprint`. The runner delegates to the same helper; same
  record shape, design D4 of ri-06.
- `resolve_parked(attempt, *, workspace, repo_root, adapter, evaluator=None, now=None) -> ParkedResolution`.
- `require_approval_ref(checkpoint, approval_ref, *, gate, dispatch_id=None, roadmap_id=None, roadmap=None) -> record`
  — raises `ApprovalRefError` unless the reference resolves; `roadmap` is required when `gate is Gate.ROADMAP_APPROVAL` (D3).
- `gate_log(workspace, repo_root) -> list[record]` — sidecar ∪ each item's child
  `gate_decisions`, resolved through the attempt's worktree (D6).

The router's `repo_root` is always the **supervisor's** repository root, never a child
worktree: `ApprovalGate.evaluate` re-reads `TRUST_POSTURE.md` from `repo_root` on every
call, and `runner._evaluate_gate` deliberately uses the child's `Path.cwd()` so a child
decides under the posture committed on its own branch. Re-evaluating a parked child under
the supervisor's posture is therefore the intended hot-reload seam (D4 step 1), and it is
also why a posture edit must be committed before it reaches a running child.

A test asserts by AST that the names `ApprovalGate`, `build_default_gate`, and
`check_filed`, and any `.evaluate(...)` whose receiver is an approval-gate object, appear
in no supervise script other than `gate_router.py`. The scan deliberately does **not**
forbid a bare `.evaluate(` token: `cycle_state.py` calls the router's own module-level
`evaluate` / `answer` / `resolve_parked`, and that call is the seam working, not a bypass.

`cycle_state.py` and `gate_router.py` reference each other (the router projects through
`cycle_state.write_mirror`; the subcommands call the router), and `cycle_state.py` does
heavy import-time work in `_load_runtime_models`. Both directions therefore import lazily
inside the calling function, never at module top level.

### D3 — `approval_ref` is `gate-decision:<decision_id>` and must resolve, and a `roadmap_approval` reference must still match the roadmap's shape

`require_approval_ref(checkpoint, approval_ref, *, gate, dispatch_id=None, roadmap_id=None, roadmap=None)` gains a `roadmap: Roadmap | None` keyword, required exactly when `gate is Gate.ROADMAP_APPROVAL`, so the fingerprint recompute below has a DAG to hash against — `Checkpoint` itself carries no item shape. `ExecutionAdapter.prepare` loads `roadmap.yaml` (the same file `cycle_state.py` reads) before calling it, so the check runs against the roadmap's on-disk state at prepare-time, not at the time the reference was minted.
`ExecutionAdapter.resume(...)` calls `require_approval_ref(checkpoint, ref, gate=<parked gate or
escalate_resume>, dispatch_id=…)`; the record must have `outcome == "proceed"`. `prepare`
holds no checkpoint today — it validates isolation and delegates straight to
`prepare_delegated_batch` — so it loads one (`CheckpointManager(workspace, repo_root).load()`)
solely to resolve the reference, and does so before `prepare_delegated_batch` writes any
attempt. A workspace with no checkpoint at that point means nothing recorded the approval, so
the `FileNotFoundError` is reported as the missing-approval refusal rather than propagated.
The `resume` check runs
on the loaded attempt **before** `_remove_owned_marker` and the field strip, because `resume`
pops `parked` as part of the transition — so the expected gate must be read from
`attempt["parked"]["gate"]` while it still exists, and a rejected reference must leave the
attempt untouched, as the roadmap-orchestration scenario requires. `prepare(...)`
gains a required keyword `roadmap_approval_ref` checked against a `roadmap_approval` record for
`checkpoint.roadmap_id`. The `continuation.approval_ref` schema gains the uuid4 pattern in
`contracts/schemas/delegated-dispatch-attempt.continuation.patch.json` (`^gate-decision:` +
8-4-4-4-12 hex); the same pattern is applied to the echo in
`supervised-dispatch-request.schema.json`. Provenance is checked against the **tracked**
ledger: whoever can write `checkpoint.json` can forge a record, which is exactly the trust
boundary `TRUST_POSTURE.md` itself sits on (repository write access), so no signing is
added. Test fixtures get `approve_roadmap(workspace)` / `approve_parked(workspace, attempt)`
helpers that record console decisions.

The subject-key dedup in D4 step 0 stops a *fresh* `gate-check` from reusing a stale decision, but a caller that retained an old `gate-decision:<id>` string across a `refine-roadmap` or replan is not going through `gate-check` at all — the reference alone would still satisfy `require_approval_ref`'s outcome/gate/roadmap_id checks. Closing that, `require_approval_ref` recomputes `roadmap_fingerprint(roadmap)` for the checkpoint's roadmap and rejects a `roadmap_approval` record whose stamped `roadmap_fingerprint` differs, with the same refusal shape as an unresolvable reference (`ApprovalRefError`, "Refuse unapproved roadmap execution"). Only `roadmap_approval` records carry a fingerprint; the check is skipped for every other gate Because every `roadmap_approval` record is now stamped regardless of which router path produced it (D2), the recompute-and-compare has a value to check on every reference `prepare` sees.

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
   after filing) → call `ApprovalGate.check_filed(gate, approval_id, notified=…)` first. It
   wraps the gate service's own `_interpret_status`: `approved` → `PROCEED/approved`, `denied`
   → `BLOCKED/rejected`, `expired` → the default action, `pending` → `None`. Two arguments
   `_interpret_status` needs cannot be recovered from an `approval_id` alone, so the router
   supplies them: the `GateDisposition` comes from the **live** posture (consistent with the
   hot-reload rule — a posture flip between cycles is meant to be honoured), and `notified`
   is read from the prior record's own `notified` field (stamped at filing time per D2) rather
   than defaulting to `True`. That second point is a
   security property, not a detail: `_apply_default` fails a `default_action: proceed` gate
   closed when `notified` is false, and `BridgeCoordinatorClient.push_notification` always
   returns `False` today (ri-05), so a `check_filed` that assumed delivery could turn an
   `expired` status into a `proceed` that unparks work no human was ever told about. With
   `notified=False` the `expired` arm returns `None` and the fail-closed block stands. A
   non-`None`
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
   `requested_at + DEFAULT_BLOCK_HORIZON` otherwise — the record schema requires a deadline
   and a blocked gate has none of its own. `DEFAULT_BLOCK_HORIZON` is new (7 days, a module
   constant in `gate_router.py`): neither `autopilot.build_gate_request` nor `cycle_state`
   has a precedent to reuse, since autopilot's `pending_gate` carries no deadline and
   `_clean_pending_gate` only validates that one is present.

### D5 — `cycle` gate protocol replaces the prose stop
`cycle_state.py gate-check --roadmap <id> [--context K=V…]` evaluates `roadmap_approval` with
`{roadmap_id, item_count, roadmap_fingerprint}`, where `roadmap_fingerprint` is the sha256 of
the roadmap's sorted `(item_id, change_id, sorted(depends_on), sorted(external_depends_on),
normalized_status)` tuples — the shape the operator authorized, not its progress — so an
approved roadmap is asked once and re-asked only when `refine-roadmap` or a replan changes
that shape (this answers the plan-phase open question: a `proceed` decision has no time
expiry, `standing_decisions.expires_at` stays `null`, and expiry is structural).
`external_depends_on` is in the tuple because `cycle_state.py ready` resolves external edges
to decide what runs, so a changed external edge changes what an approval authorizes;
`normalized_status` collapses the progress statuses to one value but keeps `superseded` and
`skipped` (`cycle_state._CEDED`) distinct, because `refine-roadmap` superseding an item
narrows the approved scope without touching any `item_id`, `change_id`, or `depends_on`.
Without those two components an approval could silently outlive the DAG it was given for.

Exit codes reuse `runner.py gate-check`'s numbers deliberately, with one documented
divergence: 3 = proceed (SKILL continues into `/plan-roadmap`
approval and `execute`; a reused decision also exits 3 and prints the reused record), 0 =
parked on `posture_block` (prints the pending entry; SKILL renders it under "Needs a decision"
and stops), 4 = blocked terminally (`rejected`, `timeout_default_block`,
`coordinator_unreachable`; the entry is printed with its resolution and the SKILL stops — the
operator may still answer it with `gate-answer`, since a human answer satisfies every
disposition). **That last clause is the divergence**: `runner.py`'s `EXIT_GATE_PARKED = 4`
means the run entered ESCALATE and cleared `pending_gate`, so `runner.py gate-answer` refuses
it as "no gate pending". Supervise's exit 4 keeps the `pending_gates` entry answerable on
purpose, because the supervisor has no ESCALATE state to fall into and the operator is the
only way forward. The SKILL protocol block states the difference so nobody carries runner's
reading across. Under `notify_with_timeout` a `gate-check` waits up to the posture's
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

Two protocol rules complete the picture. **`execute` always starts with `gate-check`**: the
`### Approval gate` section runs `gate-check --roadmap <id>`; exit 3 prints the (usually reused)
record whose `decision_id` becomes the `roadmap_approval_ref` handed to `prepare`, exit 0 / 4
stops before `prepare` — so a rehydrated `execute` session never has to find the approval in
conversation history, and "Refuse unapproved roadmap execution" is the exit-0 path.
**`cycle --dry-run` never runs `gate-check`**: a dry run stops at the digest, since evaluating
would append to `checkpoint.json` and project into the mirror, and a dry run writes no
supervisor state by contract.

### D7 — The router projects gate state into the supervisor record's mirror
`pending_gates` and `standing_decisions` are non-derivable sections that
`build_supervisor_record` only carries forward from the prior record; today nothing
deterministic adds or removes an entry. The router becomes that writer, and it writes the
tracked mirror (`openspec/supervise/supervisor-record.json`) rather than the coordinator
handoff, because the mirror is what `rehydrate` prefers when its `written_at` is newer:
- `BLOCKED` (posture_block, terminal block, or re-surface of an existing entry) → upsert a
  `pending_gates` entry keyed by `decision_id`, `{gate, change_id, requested_at, deadline,
  disposition, approval_id, decision_id, source: "supervise"}`; `change_id` is the parked
  attempt's change for a child gate, and for `roadmap_approval` it is the roadmap's first
  ready item's change, falling back to the first item carrying a `change_id` when nothing is
  ready. `$defs.pendingGate` makes `change_id` required and `_clean_pending_gate` drops any
  entry failing `^[a-z0-9]+(-[a-z0-9]+)*$`, so a roadmap naming no change at all cannot be
  projected: the router refuses the gate with a reported reason rather than parking an entry
  that would silently vanish on write.

`decision_id` needs one code change to survive the write. `_clean_pending_gate`
(`cycle_state.py`) is an **allowlist**: it rebuilds each entry from `gate`, `change_id`,
`requested_at`, `deadline`, and optional `disposition` / `approval_id` / `source`, dropping
everything else — so an unmodified cleaner strips `decision_id` and the projection key never
reaches a rehydrated session. The same function rejects any entry whose `gate` is outside
`_GATES`, which is still the eight-name literal until the enum import lands. Both edits
therefore belong to `cycle_state.py` and must precede the projection, which is why they are
task 2.0 — ordered ahead of the router tests and implementation, rather than after 2.7 where
the enum swap originally sat.

`write_mirror(repo_root, record, *, now)` is a whole-record replace, not a patch: it derives
`pending_gates`, `standing_decisions`, and `back_edge` from its `record` argument alone via
`_durable_sections`. The router therefore reads the currently selected durable state first
(the mirror, or `rehydrate`'s selection when the handoff is newer), merges its upsert or
removal into all three sections, and passes the merged record — otherwise a projection would
erase `back_edge` and every unrelated standing decision.

One consequence to state rather than discover: `_tree_listing` excludes only `LEDGER_PATH`
and `MIRROR_PATH`, and `openspec/roadmaps/<id>/checkpoint.json` is tracked. Appending a gate
decision therefore *does* move `compute_fingerprint`. Only the reuse and re-surface paths are
fingerprint-neutral; a first evaluation deliberately marks the tree as changed, and a blocked
gate settles on the following cycle, when the prior-record rule writes nothing.
- `PROCEED` (evaluate, `check_filed`, console answer, or reuse) → remove every
  `pending_gates` entry for the same subject key; for `roadmap_approval` also upsert the
  standing decision from D5.
- `BLOCKED/rejected` or `console_rejected` → the entry stays, with its `disposition`, so the
  digest keeps showing the terminal answer until the subject key changes.
Writes go through the existing `cycle_state.write_mirror` (atomic, schema-validated,
idempotent — an unchanged section preserves `written_at`, so a reused decision leaves the
cycle fingerprint untouched). The mirror path is inside `_ALLOWED_WRITE_PREFIXES`
(`openspec/supervise/`), as is `openspec/roadmaps/<id>/checkpoint.json`, so `audit-since`
passes. The `cycle` SKILL's final record step must **re-select** the prior at write time
(`rehydrate --handoff "$SUPERVISE_HANDOFF"` again, not `supervisor-record --prior
"$SUPERVISE_RECORD"` captured before the gate ran); otherwise the pre-gate snapshot would
overwrite the router's projection. Task 3.2 makes that edit; task 2.1 pins the projection.

### D6 — The evaluation log is durable local state; coordinator memory is best-effort
`gate-log --roadmap <id>` reads the workspace's `checkpoint.json` `gate_decisions` plus each
item's child `gate_decisions`, prints one JSON array sorted by `recorded_at`, and tags each
record with its `origin` (`checkpoint` or the change id). `BridgeAuditSink` remains the remote
path (unchanged, never raises). Acceptance outcome 2 is verified against `gate-log`.

The child half cannot be read from the supervisor's own tree. `loop-state.json` is untracked
per-worktree state — `git ls-files openspec/changes` returns loop-state files only under
`archive/`, and a second worktree of the same branch does not have one — and a child's copy
lives in that child's isolated worktree, not in the supervisor's `openspec/changes/<id>/`. So
`gate-log` resolves each item through the attempt the checkpoint already records: its
`isolation.worktree_path`, or the result's `evidence.loop_state_path`, falling back to the
supervisor path only for a change that has since merged. A child whose loop state cannot be
read is reported as a degraded origin, never omitted silently, because a missing origin and an
empty one are the difference between "no gates fired" and "the log is incomplete". The e2e
test (task 2.10) must place at least one child's loop state outside the supervisor repo root,
or it would pass on a co-located tmp tree while the real path finds nothing.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Prose-free gates: 0 `Gate` names in `skills/supervise/SKILL.md` outside protocol blocks | `skills/tests/supervise/test_prose_free_gates.py` (mirrors `skills/tests/autopilot/test_prose_free_gates.py`) | new |
| Decision provenance: 0 unresolvable `approval_ref` accepted | `test_execution.py::test_resume_rejects_unresolvable_ref`, `test_prepare_refuses_without_roadmap_approval`, `test_gate_router.py::test_require_approval_ref_*` | new |
| Evaluation completeness: 0 evaluations without a record in a full simulated run | `test_gate_router_e2e.py` (fake coordinator + in-memory evaluator; asserts `gate-log` covers every evaluate call and every `approval_ref`) | new |
| Hot reload: posture edits reflected at next evaluation | `test_gate_router.py::test_parked_child_unparks_after_posture_flip` | new |
| Ask once: an approved roadmap is not re-asked until its DAG changes | `test_gate_router.py::test_roadmap_approval_reused_until_fingerprint_changes` | new |
| Late answer honoured, nothing re-filed: a coordinator approval answered after the local timeout resolves on the next cycle without a second request | `test_gate_router.py::test_check_filed_before_refiling`, `shared/tests/test_approval_gate.py::test_check_filed_*` | new |
| An undelivered notification is never upgraded to proceed: `expired` + `notified=False` leaves the fail-closed block standing | `shared/tests/test_approval_gate.py::test_check_filed_expired_undelivered_stays_blocked` | new |
| Ask-once cannot outlive its scope: a superseded item or a changed external edge moves the fingerprint | `test_gate_router.py::test_roadmap_fingerprint_covers_status_and_external_edges` | new |
| The evaluation log reaches child worktrees: `gate-log` resolves a child's loop state through the attempt's worktree, not the supervisor's tree | `test_gate_router_e2e.py` (child loop state placed outside the supervisor repo root) | new |
| First `gate-check` on a workspace with no `checkpoint.json` bootstraps instead of raising | `test_cycle_state.py::test_gate_check_bootstraps_missing_checkpoint` | new |
| Originating console answer is limited to `roadmap_approval` | `test_cycle_state.py::test_gate_answer_refuses_unparked_gate` | new |
| Projection: a blocked decision appears in the mirror's `pending_gates` and disappears on proceed; a reused decision writes nothing | `test_gate_router.py::test_projection_*`, `test_gate_router_e2e.py` (rehydrate after each step shows the entry) | new |
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
| The `prepare` argument and the `approval_ref` pattern also break `skills/tests/autopilot-roadmap/`, which no package could write: `test_supervised_dispatch_e2e.py` calls `adapter.prepare(...)` directly, and `test_supervised_dispatch.py` writes `approval_ref: "approval-1"` into a checkpoint that `apply_delegated_batch` validates | Both files added to wp-router's `write_allow`, lock set, and tasks 2.5/2.6 — wp-router's own verification runs `tests/autopilot-roadmap`, so without this the package cannot make its own gate green |
| Nine-gate growth breaks "eight" assertions in `shared/tests`, autopilot tests, spec text | All sites enumerated in tasks 1.x; `test_gate_call_sites` unaffected (it iterates autopilot's seven and asserts `replan_required` is not autopilot's — `roadmap_approval` is added to that non-autopilot set) |
| `add-supervisor-candidate-work-digest` rewrites `cycle` §2–§5 of `SKILL.md` (it does not touch `cycle_state.py`) | It is unstarted; task 3.4 leaves a rebase note naming the §5 protocol block; this change's `SKILL.md` edits stay inside §5, `### Approval gate`, and `### Reconcile and resume` |
| `test_workflow_contract.py` slices `SKILL.md` on `## Verb: \`execute\``, `### Approval gate`, `### Prepare and launch`, `### Reconcile and resume`, pins ``durable `approval_ref` ``, **and** pins six separate phrases inside `### Approval gate` | Task 3.2 keeps the headings and the `approval_ref` phrase, but `test_execute_requires_one_durable_roadmap_altitude_approval_before_mutation` must be updated in the same commit: its `before any roadmap checkpoint or execution-state mutation` assertion becomes false by design, since `gate-check` appends the gate-decision record to `checkpoint.json` before any approval exists. That ledger write is the one checkpoint mutation that legitimately precedes approval |
| A supervise prose-free test that mirrors `test_prose_free_gates.py` inherits its `test_mirror_is_byte_identical` cases, which wp-skill-docs cannot satisfy: `install.sh` runs in wp-integration (task 4.1) and `.claude/skills/**` is outside wp-skill-docs' `write_allow` | Task 3.1 states that the supervise test carries no mirror-parity case; mirror resync stays wp-integration's job and is already covered for `supervise` by task 4.1 |
| A forged `proceed` record in the tracked ledger would pass `require_approval_ref` | Same trust boundary as `TRUST_POSTURE.md` (repository write access); the ledger is reviewed in the PR like any tracked file; no signing (out of scope) |
| Re-notification under `notify_with_timeout` | Bounded by D4 step 0.3: one request per expired approval per operator-run cycle; a `pending` server status is never re-filed |
| The `cycle` SKILL's final `supervisor-record --prior "$SUPERVISE_RECORD"` step would overwrite the router's mirror projection with the pre-gate snapshot | D7: the final step re-selects the prior via `rehydrate`; the e2e test rehydrates after `gate-check` and after the final write and asserts the entry survives |
| Coordinator unreachable during `notify_with_timeout` | Unchanged `ApprovalGate` semantics: `coordinator_unreachable` → BLOCKED, recorded, surfaced |
| `BridgeCoordinatorClient.push_notification` always returns `False` (diagnostic endpoint) so `default_action: proceed` fails closed | Pre-existing ri-05 behaviour; documented in the SKILL, not changed here |

## Migration Plan

1. Land contracts first (enum, template, schemas, tests) — additive, no behaviour change.
2. Land the router, `execution.py` checks, and `cycle_state.py` subcommands with tests.
3. Land `SKILL.md` edits and the prose-free test; run `install.sh` to resync runtime mirrors.
4. Rollback: revert the change; persisted `gate_decisions` records with extra fields remain
   schema-valid; a `TRUST_POSTURE.md` carrying `roadmap_approval` would fail validation against
   the old schema, so the rollback note tells operators to drop that key.
