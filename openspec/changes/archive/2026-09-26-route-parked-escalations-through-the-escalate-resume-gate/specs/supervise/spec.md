## ADDED Requirements

### Requirement: Immediate Policy-Pause Escalation Has One Authoritative Commit

After complete durable application of a named delegated batch, the supervise runtime SHALL route each parked `policy_pause` through `escalate_resume`. It SHALL use a process-safe generation subject lock for external evaluation and a short shared checkpoint transaction for fresh authority updates. The transaction SHALL serialize the gate-decision ledger with checkpoint state and, for proceed, SHALL atomically record the decision and advance only the matching parked attempt to its next generation. It SHALL NOT hold the checkpoint transaction across approval-service I/O, notification polling, or host callbacks. Supervisor mirror and handoff state SHALL be derived from the committed ledger, never authority for resume.

#### Scenario: Complete batch routes exactly once

- **WHEN** every named-batch attempt is terminal with application journal state `effects_applied` and one is parked as `policy_pause`
- **THEN** the runtime SHALL evaluate or reuse exactly one `escalate_resume` decision for that dispatch and parked generation
- **AND** a proceed SHALL create its generation G+1 continuation in the same authoritative transaction
- **AND** a blocked decision SHALL leave the attempt parked and project one normalized pending gate after that transaction

#### Scenario: Partial batch cannot route

- **WHEN** any member of the named batch is not terminal with application journal state `effects_applied`
- **THEN** route operation SHALL refuse before evaluation, notification, projection, or resume
- **AND** application recovery SHALL remain replayable without a second host callback

#### Scenario: Approval wait preserves concurrent authority

- **WHEN** routing waits for an approval decision while a different execution transition commits in the same workspace
- **THEN** the unrelated transition SHALL remain durable after routing commits
- **AND** the workspace transaction SHALL not be held during the wait
- **AND** the committed checkpoint SHALL never expose the new state without its decision ledger update

#### Scenario: Stale and concurrent routing are safe

- **WHEN** the routed attempt changes state or generation while a candidate decision waits
- **THEN** the stale candidate SHALL not append a record, alter the mirror, or resume the attempt
- **AND** when automatic and manual resolution race for the same generation, only one authoritative decision and optional resume SHALL occur
- **AND** concurrent blocked decisions for different subjects SHALL preserve both normalized mirror entries

### Requirement: Escalate Resume Correlation Is Generation-Safe and Sanitized

New `escalate_resume` records SHALL carry the parked positive integer `lease_generation`; prior generationless records SHALL remain reusable for the matching currently parked dispatch. Every policy-pause resolver, including manual reconciliation, SHALL use only the allowlisted context `dispatch_id`, `change_id`, `item_id`, `lease_generation`, `verb: resume`, and fixed retry-budget reason. Approval references SHALL authorize the same parked generation only.

#### Scenario: Legacy and later generations remain distinct

- **WHEN** a current parked dispatch has a generationless legacy escalation record
- **THEN** the router SHALL reuse it without filing a duplicate approval
- **AND** when that dispatch later parks at a higher generation, it SHALL create a new decision and retire older same-dispatch pending mirror entries
- **AND** a prior-generation proceed reference SHALL be rejected

#### Scenario: Manual and automatic context are identical

- **WHEN** either automatic post-apply routing or manual reconciliation resolves a policy pause
- **THEN** its request context SHALL contain exactly the six allowlisted fields and fixed reason
- **AND** no child-provided reason, transcript, raw approval response, or additional key SHALL be persisted or returned

#### Scenario: Answer selects a generation safely

- **WHEN** an operator answers `escalate_resume` with only a dispatch ID
- **THEN** the router SHALL select the newest blocked generation
- **AND** an optional explicit generation SHALL select only that blocked generation

#### Scenario: Authoritative decision repairs a failed mirror projection

- **WHEN** a blocked escalation decision commits but its post-commit mirror projection fails
- **THEN** the checkpoint ledger SHALL remain authoritative and durable
- **AND** rehydrate SHALL idempotently rebuild the normalized pending gate from that ledger before exposing pending gates to an operator

#### Scenario: Proceed clears the prior generation journal atomically

- **WHEN** an `escalate_resume` proceed authorizes a parked generation G
- **THEN** the same shared checkpoint transaction SHALL record the decision, clear generation-G terminal fields including `application_journal`, and create the prepared G+1 continuation
- **AND** the resumed attempt SHALL be included in the current unapplied apply cohort

## MODIFIED Requirements

### Requirement: Supervise Gate Routing

The supervise skill SHALL evaluate every gate it raises — `roadmap_approval` at the end of `cycle`, the `execute` precondition, and the resolution of parked `pending_gate` and `policy_pause` attempts — exclusively through `skills/supervise/scripts/gate_router.py`, which SHALL call `shared.approval_gate.ApprovalGate.evaluate` against the supervisor repository root's `TRUST_POSTURE.md`. Whenever the router produces a new decision it SHALL append a `gate-decision.schema.json` record carrying `decision_id`, `source: "supervise"`, `verb`, `roadmap_id`, and any correlating `change_id` / `dispatch_id` to the roadmap workspace's `checkpoint.json` `gate_decisions` ledger before acting on that decision; reusing or re-surfacing a prior record SHALL append nothing. When the workspace has no `checkpoint.json` the router SHALL create one from the roadmap before recording, and `gate-log` SHALL report an absent workspace as empty rather than failing. Records SHALL be built with `shared.approval_gate.build_gate_decision_record` and console answers with `shared.approval_gate.console_decision`; the router SHALL NOT import `autopilot.py`. Before evaluating, the router SHALL apply a prior-record rule to the ledger keyed by the decision's subject (`gate`, `roadmap_id`, and `dispatch_id` for parked attempts or `roadmap_fingerprint` for `roadmap_approval`): a `proceed` record is reused without evaluating; an open `posture_block` record is re-surfaced unchanged unless the posture's disposition for that gate changed; a blocked record carrying an `approval_id` is checked through `ApprovalGate.check_filed` before any new approval is filed; a `rejected` or `console_rejected` record is terminal until the subject changes or a console answer is recorded. `check_filed` SHALL NOT upgrade a prior fail-closed block to `proceed`: it SHALL be called with `notified` sourced from the prior record's own `notified` field (never a literal or a default), and when the coordinator reports `expired` and that `notified` value is `False`, it SHALL return no decision rather than apply a `proceed` default. No other module under `skills/supervise/scripts/` SHALL import or call the approval gate. `cycle_state.py` SHALL expose `gate-check`, `gate-answer`, and `gate-log` subcommands and SHALL import the `Gate` and `Disposition` enums from `shared.trust_posture` rather than duplicating them. `gate-answer` SHALL require a prior parked record for every gate except `roadmap_approval`, whose console answer MAY originate a record; the posture snapshot a console answer records SHALL come from the router's own prior blocked record for that subject, or from the live posture when the answer originates one. The router SHALL project every blocked decision into the tracked mirror's `pending_gates` (keyed by `decision_id`) and every `proceed` decision out of it — upserting the `roadmap_approval` standing decision — through `cycle_state.write_mirror`, merging its change into the currently selected durable state so `back_edge` and unrelated standing decisions survive, and a reused decision SHALL leave the mirror untouched. `cycle_state._clean_pending_gate` SHALL carry `decision_id` through, since it is an allowlist that would otherwise strip the projection key. `gate-check` SHALL NOT run under `cycle --dry-run`, and `execute` SHALL begin with `gate-check`, whose exit-3 record supplies the `roadmap_approval_ref`. `skills/supervise/SKILL.md` SHALL contain no gate whose only enforcement is prose.

#### Scenario: Auto posture takes a conversation to execution without a human touch
- **GIVEN** a `TRUST_POSTURE.md` with `roadmap_approval: auto`
- **WHEN** `cycle_state.py gate-check --roadmap R` runs after the digest
- **THEN** it records a `roadmap_approval` decision with resolution `auto` and exits 3
- **AND** the skill proceeds into `/plan-roadmap` approval and `execute` without asking the operator

#### Scenario: Block posture parks the roadmap approval for a console answer
- **GIVEN** no `TRUST_POSTURE.md` (or `roadmap_approval: block`)
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it records a `posture_block` decision, prints a `pending_gates` entry with `gate: roadmap_approval`, a deadline, and `source: supervise`, and exits 0
- **AND** `gate-answer --roadmap R --gate roadmap_approval --decision approved` records a `console_approved` decision, mirrors it into `standing_decisions`, and prints the `roadmap_approval_ref`

#### Scenario: Notify posture waits for the posture timeout and honours a late answer without re-filing
- **GIVEN** `roadmap_approval: notify_with_timeout` with `timeout_seconds: T` and `default_action: block`, and a reachable coordinator that leaves the approval unanswered
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it files exactly one approval request, waits no longer than T, records a `timeout_default_block` decision carrying the `approval_id`, prints a `pending_gates` entry whose `deadline` is `requested_at + T`, and exits 4
- **AND** when the operator approves that request in the coordinator after the timeout and the next `gate-check --roadmap R` runs, the router calls `ApprovalGate.check_filed(Gate.ROADMAP_APPROVAL, approval_id, notified=False)` — `notified` sourced from the timed-out record's own field, and `False` here because `default_action: block` reached the timeout with no delivery — records an `approved` decision with outcome `proceed`, files no second request, and exits 3
- **AND** when the coordinator still reports the request `pending`, the second run re-surfaces the same entry and deadline and files nothing

#### Scenario: Approved roadmap is not re-asked until its DAG changes
- **GIVEN** a `proceed` `roadmap_approval` record for roadmap R whose `roadmap_fingerprint` matches R's current sorted `(item_id, change_id, depends_on, external_depends_on, status)` tuples, where `status` is normalized so completion-only transitions do not change it
- **WHEN** `gate-check --roadmap R` runs again after an item of R completes
- **THEN** it reuses the existing record, appends nothing to the ledger, prints the reused record, and exits 3
- **AND** when `refine-roadmap` adds, splits, or supersedes an item, or an external dependency edge changes, so the fingerprint changes, the next `gate-check` evaluates `roadmap_approval` anew

#### Scenario: Direct invocation records an originating console decision
- **WHEN** `/autopilot-roadmap` is invoked directly and runs `gate-answer --roadmap R --gate roadmap_approval --decision approved --note "direct invocation"` with no prior parked record
- **THEN** a `console_approved` `roadmap_approval` decision with outcome `proceed` is recorded, its posture snapshot taken from the live posture, and `roadmap_approval_ref` is printed
- **AND** `gate-answer --gate pr_creation` for a dispatch with no parked record is refused without recording anything

#### Scenario: Parked child unparks after a posture flip
- **GIVEN** a `pending_gate` attempt parked on `pr_creation` under `block`
- **WHEN** the operator edits `TRUST_POSTURE.md` to `pr_creation: auto` and the supervisor runs `resolve_parked`
- **THEN** the router records an `auto` decision and calls `ExecutionAdapter.resume` with `approval_ref = gate-decision:<decision_id>`
- **AND** no console answer is required

#### Scenario: Policy pause resolves through escalate_resume
- **WHEN** a `policy_pause` attempt (child in `ESCALATE`) is resolved
- **THEN** the router evaluates `Gate.ESCALATE_RESUME`, not a new gate
- **AND** a `BLOCKED` decision leaves the attempt parked and surfaces `escalate_resume` in `pending_gates`

#### Scenario: Evaluation log covers every supervised gate
- **WHEN** a full simulated run (cycle → execute → parked child → resume) completes and `cycle_state.py gate-log --roadmap R` runs
- **THEN** the output lists one record per `ApprovalGate.evaluate`, `check_filed` decision, or console answer made by the supervisor — and none for a reused or re-surfaced record — plus each item's child `gate_decisions`, each with the posture disposition that was applied and its origin
- **AND** each child's `loop-state.json` SHALL be resolved through the attempt's recorded worktree (`isolation.worktree_path`, or the result's `evidence.loop_state_path`) rather than the supervisor's own `openspec/changes/<change_id>/`, because a child's loop state is untracked and lives only in that child's worktree
- **AND** a child whose loop state cannot be read SHALL be reported as a degraded origin rather than omitted silently
- **AND** every `approval_ref` used during the run resolves to one of those records

#### Scenario: Router is the only seam
- **WHEN** the test scans `skills/supervise/scripts/*.py` by AST
- **THEN** the names `ApprovalGate`, `build_default_gate`, and `check_filed`, and any `.evaluate(...)` call whose receiver is an approval-gate object, appear only in `gate_router.py`
- **AND** `cycle_state.py` MAY call the router's own module-level `evaluate` / `answer` / `resolve_parked` functions, which the scan SHALL NOT treat as a gate-service call site
- **AND** no module under `skills/supervise/scripts/` imports `autopilot`

#### Scenario: Unknown parked gate is a schema error, not a decision
- **WHEN** a parked snapshot names a gate outside `trust_posture.Gate`, or is of kind `pending_gate` with a null `gate` (which the result contract permits)
- **THEN** `resolve_parked` raises without recording a decision or resuming
- **AND** the attempt stays parked

#### Scenario: Router projects gate state into the mirror a fresh session rehydrates
- **GIVEN** no `TRUST_POSTURE.md` and a handoff `supervisor_record` written at T1
- **WHEN** `gate-check --roadmap R` parks `roadmap_approval` at T2 > T1 and a fresh session runs `cycle_state.py rehydrate`
- **THEN** the rehydrated record's `pending_gates` contains the entry with that `decision_id`, `disposition: block`, `source: supervise`, and a deadline, sourced from the mirror
- **AND** the entry's `change_id` is R's first ready item's change, falling back to R's first item carrying a `change_id` when no item is ready, and the gate SHALL be refused with a reported reason rather than parked when R names no change at all
- **AND** the projection preserves the prior record's `back_edge` and every standing decision it did not itself upsert
- **AND** after `gate-answer --roadmap R --gate roadmap_approval --decision approved` the next rehydrate shows no such entry and a standing decision `roadmap_approval:proceed` scoped to R
- **AND** a subsequent `gate-check --roadmap R` that reuses the decision leaves the mirror's `written_at` unchanged

For `escalate_resume`, the prior-record subject and resume authorization SHALL include the parked `lease_generation` in addition to the existing gate, roadmap, and dispatch correlation. A generationless legacy record SHALL be reusable for the matching current parked dispatch only; later generations SHALL require a new decision. Other gates retain the existing subject identity.

#### Scenario: Resume rejects a generation-blind stale reference

- **WHEN** a dispatch has later parked after a prior-generation `escalate_resume` proceed
- **THEN** `require_approval_ref` SHALL reject that prior reference for the later parked generation
- **AND** a matching legacy generationless record SHALL be reused without duplicate filing
