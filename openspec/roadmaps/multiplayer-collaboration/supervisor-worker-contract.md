# Supervisor–Worker Dispatch Contract: Findings and Proposal

Input for `/refine-roadmap multiplayer-collaboration` (operator-requested, 2026-10-06).
Evidence comes from the first `/supervise execute` run of this roadmap (2026-10-05/06):
four workers (ri-01, ri-02, ri-05, ri-20) ran in cloud sessions, and no item reached
implementation. Every stall traced back to the boundary between the supervisor and
its workers.

## The root cause

The boundary has no published contract. The dispatch **request** and **result** exist
only as inline validation in `skills/supervise/scripts/execution.py` (`_RESULT_REQUIRED`,
`_validate_result`), in `skills/autopilot-roadmap/scripts/orchestrator.py`
(`_validate_dispatch_result`) and in test fixtures. `openspec/schemas/` has
`checkpoint`, `gate-decision` and `gate-request` schemas but nothing for dispatch.
Each worker prompt therefore restated the result shape by hand, and every behavior the
prompt did not spell out was left to the worker's judgement. The four issues below all
arise in those gaps.

## Issue 1: a parked gate does not follow a posture change

*Observed:* ri-01 parked at `proposal_approval` while no `TRUST_POSTURE.md` existed, so
the disposition defaulted to `block`. The operator then adopted a posture with
`proposal_approval: auto`. The supervisor-side record resolved to `proceed`, but the
child's `loop-state.json` still held the old `pending_gate`, and `runner.py gate-check`
never re-evaluates a pending gate. The worker parked a second time.

*Contract gap:* one gate has two state holders (the child's `loop-state.pending_gate`
and the supervisor's `checkpoint.gate_decisions`), and no rule says which one is
authoritative or how an answer travels from one to the other. A decision derived from
posture was treated as sticky in the same way a human decision is.

*Contract clause:*
- Every gate decision records its **provenance**: `posture` (with the digest of the
  posture it was evaluated under) or `human` (with an `approval_ref`).
- Posture-derived blocks are re-evaluated on resume whenever the current posture digest
  differs. Human decisions are never silently overridden.
- Answers flow in one direction, from supervisor to child, as a typed **gate answer**
  carried in the resume request (`gate`, `decision`, `approval_ref`). The child applies it
  through `runner.py gate-answer` with `--approval-ref`. The supervisor never edits a
  child worktree to answer a gate; doing that by hand on 2026-10-05 is exactly what this
  clause replaces.

## Issue 2: probing the environment for capabilities hits permission prompts

*Observed:* review sub-agents probed vendor availability with
`env | grep <API key names>`. The repo's `.claude/settings.json` deliberately lists
`env *` under `ask`, and auto mode flags credential probing. Three of the four workers
sat in `REQUIRES_ACTION` for hours. A plain read-only `cat` was also refused once by the
classifier. No worker had a channel to say "blocked on a permission"; the supervisor
found out only by polling `get_session`.

*Contract gap:* workers discover their own capabilities by inspecting the environment,
and a blocked state has no representation in the protocol.

*Contract clause:*
- The **request** carries an `execution_profile` resolved by the supervisor before
  launch: the verified vendor lanes per mode (`review`, `alternative`, `quick`),
  location, isolation, and the sanctioned probe command a worker may re-run
  (`review_dispatcher.py --check-vendors`). Workers must not read credentials or
  environment variables to discover capabilities.
- A new parked kind, `permission_blocked` (tool, a redacted command, the classifier
  reason), lets a worker that is denied a permission **return** instead of waiting. The
  supervisor routes it to the operator as one escalation, deduplicated per rule.

## Issue 3: review degrades silently below quorum

*Observed:* ri-05's plan review ran with `min_quorum=1` because `--check-vendors`
reported `codex` as available even though no codex CLI was installed. Review stopped at
`max_iter` / `adjudication_required`, which then looked like a design disagreement.
Degradations (one vendor, coordinator `forbidden`, audit sink failures) appeared only in
prose bullets.

*Contract gap:* the request does not say what review quality the item requires, and the
result has no structured field for degradation.

*Contract clause:*
- The request states `review_requirements`: the minimum quorum per phase and the lanes
  that count toward it, taken from the routing cost policy (subscription-local, then
  subscription-cloud, then metered).
- Availability means **dispatchable for the requested mode**, verified by a dry
  invocation, not merely listed in the roster.
- When a quorum cannot be met, the worker returns `parked` with kind
  `capability_unavailable` (naming the missing lanes) instead of lowering the quorum.
  The supervisor can then route the review to another lane, for example the GX10 review
  queue.
- The result carries `degradations: [{code, phase, detail}]` with an enumerated code set
  (`single_vendor_review`, `coordinator_projection_forbidden`, `audit_sink_failed`,
  `phase_fallback_inline`, ...), so the supervisor can aggregate degradations instead of
  reading them out of prose.

## Issue 4: the vocabularies do not match, so a parked result can be unanswerable

*Observed:* ri-01 (generation 3) reported `kind: pending_gate, gate: escalate_resume`.
The supervisor accepts `escalate_resume` answers only for `policy_pause` parks
(`policy_pause` is defined as "supervised phase retry budget exhausted", which is also
what autopilot's `ESCALATE` state represents). The park could not be answered, so
execution deadlocked until a code fix landed (`openspec/supervise-pending-escalate-answer`).

*Contract gap:* no normative mapping exists from a child's loop state to a result kind,
and no check guarantees that every kind a child can emit has an answer path.

*Contract clause:*
- Publish versioned `openspec/schemas/dispatch-request.schema.json` and
  `dispatch-result.schema.json`. These are the only definition; `execution.py`,
  `orchestrator.py` and the fixtures validate against them.
- A normative **loop-state → result mapping**, emitted by code and never composed by
  hand: `runner.py emit-result <change-id> --dispatch-id ... --generation ...`
  produces the result JSON, including its evidence digest, from `loop-state.json`.
  - `pending_gate` set → `parked/pending_gate`, gate taken from the child.
  - `ESCALATE` → `parked/policy_pause`, carrying `previous_phase`.
  - Permission denial → `parked/permission_blocked`.
  - Quorum not met → `parked/capability_unavailable`.
  - `DONE` → `success`.
- A **closure property**, enforced by a contract test: for every `(outcome, kind, gate)`
  the schema allows, the supervisor has an answer or resume path. Applying a result the
  supervisor cannot route is refused at `apply` time, not at relaunch time.

## Cross-cutting: transport and durability

- Results reach the supervisor today through free text in a cross-session message. The
  contract should fix the transport: the result file is committed on the change branch
  at a fixed path (`openspec/changes/<id>/dispatch-results/<dispatch>-g<N>.json`), and
  the message only points to it. That makes delivery durable across restarts and lets
  verification read the same bytes.
- Pending operator decisions belong in the supervisor record (`pending_gates`), not only
  in a chat turn. During this run, two in-chat questions were lost to worker restarts.

## Proposed roadmap change

Add one item, `dispatch-contract` (priority 1, no dependencies). Make
`team-work-queue`, `owner-routed-escalation` and `queue-dispatch-owner-acceptance`
depend on it, since each of them is built on this request/result boundary. Its
acceptance outcomes:
1. Request and result schemas are published, and `execution.py` and `orchestrator.py`
   validate against them (the existing fixtures pass).
2. `runner.py emit-result` exists, and an end-to-end test shows that every loop-state
   terminal or parked shape maps to a schema-valid result.
3. A closure contract test fails if any schema-permitted parked kind/gate combination
   lacks a supervisor answer path.
4. Gate provenance plus posture-digest re-evaluation: a posture-derived block clears on
   resume after a posture change, and a human rejection does not.
5. `execution_profile`, `review_requirements` and `degradations[]` fields are present,
   and the parked kinds `permission_blocked` and `capability_unavailable` are routed
   end to end.

This item also absorbs four follow-ups noted during the run: re-evaluation of stale
gates, env-free vendor probing, honest quorum, and pending_gate/escalate_resume
answerability. For the last of these, the narrow fix is already in flight on
`openspec/supervise-pending-escalate-answer`.
