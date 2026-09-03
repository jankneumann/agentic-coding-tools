# Change: route-supervise-gates-through-the-approval-gate-service

> Parent roadmap: `roadmap-supervisor-orchestration` (item ri-04, priority 1, effort M)
> Depends on: ri-03 `wire-supervise-execution-through-the-dispatch-fn-seam` (completed),
> `roadmap-always-on-agent-automation:ri-06` `encode-autopilot-gates-and-goal-gate-in-code` (completed)
> Architecture layers: Trust (gate service, posture contract), Coordination (supervise, roadmap orchestrator)

## Why

The autopilot loop encodes its seven gates as `ApprovalGate.evaluate` call sites and the
roadmap orchestrator routes `replan_required` the same way, but the supervise skill — the
layer that is supposed to take a conversation to a merged PR with minimal interruption —
never calls the gate service at all. Its roadmap-approval gate is a paragraph in
`SKILL.md`, its `execute` precondition ("durable roadmap-altitude approval") is asserted by
prose and a contract test rather than enforced by `ExecutionAdapter.prepare`, and the
`approval_ref` that resumes a parked child is an opaque string the host session invents
with no link to any decision. Every human touchpoint above the autopilot loop therefore
bypasses `TRUST_POSTURE.md`: a posture that delegates a gate has no effect on the
supervisor, and a supervised run leaves no evaluation log for the decisions that actually
gated it.

## What Changes

- **Add a ninth gate, `roadmap_approval`, to the trust-posture contract.** The supervise
  `cycle` verb's "approve this roadmap" decision becomes a `Gate` value with a disposition
  in `TRUST_POSTURE.md` (absent file → `block`, i.e. today's chat approval). The enum,
  the template, and every schema that embeds the gate enum — `trust-posture.schema.json`,
  `gate-decision.schema.json`, `gate-request.schema.json`, `supervisor-record.schema.json`,
  and `supervisor-record-mirror.schema.json` — grow from eight to nine entries.
  (`test_gate_schemas.py::test_gate_enum_matches_trust_posture` pins `gate-request` and
  `gate-decision` to `Gate`, so all five move together or CI goes red.)
- **Add a deterministic gate router to the supervise skill**
  (`skills/supervise/scripts/gate_router.py`). It is the only path by which supervise
  evaluates a gate: it wraps `ApprovalGate.evaluate`, stamps every decision with a
  `decision_id`, `source: "supervise"`, and the correlating `roadmap_id` /
  `change_id` / `dispatch_id`, and appends it to the roadmap workspace's
  `checkpoint.json` `gate_decisions` sidecar (the same ledger the orchestrator's
  `replan_required` gate writes to). Record construction and console answers use helpers
  that this change moves into `shared.approval_gate` — `build_gate_decision_record`
  (today a private of `autopilot.py`), `console_decision` (today
  `runner._console_decision`), and a new `ApprovalGate.check_filed(gate, approval_id, *, notified)`
  that interprets a previously filed coordinator approval — so autopilot and supervise
  share one record shape and every decision, including a late coordinator answer, is
  constructed inside `approval_gate.py`. The router inherits `ApprovalGate.evaluate`'s
  synchronous semantics: under `notify_with_timeout` an evaluation files the approval,
  notifies, and waits up to the posture's `timeout_seconds` before applying the default
  action; there is no asynchronous "pending" state inside the gate service.
- **Route the three supervise gates through the router.**
  - `cycle`: after the digest, `cycle_state.py gate-check --roadmap <id>` evaluates
    `roadmap_approval`. `auto` proceeds into `/plan-roadmap` approval and `execute`;
    `notify_with_timeout` files one coordinator approval, waits up to the posture timeout,
    and on timeout surfaces the terminal decision in `pending_gates` with its
    `approval_id` (the next cycle checks that approval through `check_filed` before it
    evaluates — and re-notifies — again); `block` surfaces it and waits for
    `cycle_state.py gate-answer`. A `proceed` decision is reused by later cycles until
    the roadmap's DAG fingerprint changes, so an approved roadmap is asked once, not once
    per cycle.
  - `execute`: `ExecutionAdapter.prepare` takes a required `roadmap_approval_ref` and
    refuses to prepare unless it resolves to a `roadmap_approval` decision with outcome
    `proceed` for that roadmap. A direct `/autopilot-roadmap` invocation records an
    originating console-approved decision first (`gate-answer --gate roadmap_approval` is
    the one answer that needs no prior parked record — the operator's command is the
    human answer), so it keeps its inherited-approval semantics.
  - parked children: `gate_router.resolve_parked` re-evaluates a `pending_gate` attempt
    against the *current* posture (hot reload) — checking an already-filed coordinator
    approval before filing a new one — and a `policy_pause` attempt through
    `escalate_resume`. `PROCEED` calls `ExecutionAdapter.resume` with
    `approval_ref = "gate-decision:<decision_id>"`; `BLOCKED` records the decision and
    carries the gate into `pending_gates` with its disposition, approval id, and deadline.
- **Make `approval_ref` provable.** `ExecutionAdapter.resume` rejects any reference that
  does not resolve to a recorded gate decision with outcome `proceed`, a matching gate
  (the parked gate for `pending_gate`, `escalate_resume` for `policy_pause`), and a
  matching `dispatch_id`. The opaque-string path is removed. **BREAKING** for callers that
  passed literals; the only callers are supervise tests.
- **Expose the evaluation log.** `cycle_state.py gate-log --roadmap <id>` prints the union
  of the workspace sidecar and each item's child `gate_decisions`, so "every gate raised
  during a supervised run" is answerable from durable local state even when the
  coordinator's episodic memory is unreachable. A child's `loop-state.json` is untracked
  per-worktree state, so `gate-log` resolves it through the attempt's recorded worktree
  rather than the supervisor's own `openspec/changes/<id>/`.
- **Remove the prose gates from `skills/supervise/SKILL.md`** and extend the prose-free
  gate test to cover it. `cycle_state.py` imports the `Gate` / `Disposition` enums instead
  of duplicating them as string literals.
- No new gate prose, no new human touchpoint, and no direct LLM calls under
  `skills/supervise/scripts/`.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Governance (prose-free gates) | Occurrences of any `Gate` name in `skills/supervise/SKILL.md` outside a `gate-check` / `gate-answer` / `gate-log` protocol block | 0 | `skills/tests/supervise/test_prose_free_gates.py` (Validation) |
| Auditability (decision provenance) | `approval_ref` values accepted by `prepare` or `resume` that do not resolve to a `proceed` gate-decision record | 0 | `test_execution.py` + `test_gate_router.py` contract tests (Validation) |
| Observability (evaluation completeness) | Supervise gate evaluations in a full simulated run without a durable gate-decision record | 0 | `test_gate_router_e2e.py` full cycle→execute→park→resume run, with a child loop-state placed outside the supervisor repo root (Validation) |
| Safety (no undelivered auto-proceed) | `check_filed` decisions that turn an undelivered `default_action: proceed` timeout into `proceed` | 0 | `shared/tests/test_approval_gate.py::test_check_filed_expired_undelivered_stays_blocked` (Validation) |
| Authorization freshness | Roadmap DAG edits (superseded item, changed external edge) that do not re-ask `roadmap_approval` | 0 | `test_gate_router.py::test_roadmap_fingerprint_covers_status_and_external_edges` (Validation) |
| Operability (hot reload) | Posture edits reflected at the next gate evaluation without a process restart | 100% of evaluations | `test_gate_router.py` (Validation) |
| Compatibility (absent posture) | Behavioural difference with `TRUST_POSTURE.md` absent vs. today | none — every gate resolves to `block` and the operator answers in-conversation | `shared/tests/test_trust_posture.py` + supervise contract tests (Validation) |
| Host-assisted invariant | Direct LLM SDK or provider-network imports under `skills/supervise/scripts/` | 0 | existing host-assisted invariant test (Validation) |

## Approaches Considered

### Approach 1: Resume-seam only

Route only the parked-child resume through `ApprovalGate` (re-evaluate the child's gate,
use the decision's `approval_id` as `approval_ref`). Leave the `cycle` roadmap approval and
the `execute` precondition as prose.

- Pros: smallest diff; no change to the trust-posture contract or its eight-gate tests;
  no schema edits.
- Cons: the roadmap-altitude gate — the one human touchpoint every supervised run passes
  through — stays outside the posture, so a fully delegated posture still interrupts;
  `auto` and console decisions have no `approval_id`, so the reference has no provenance
  on exactly the paths that matter; acceptance outcome 3 ("no gate decision bypasses
  `approval_gate.py`") is unmet by construction.
- Effort: S

### Approach 2: Gate router with a ninth `roadmap_approval` gate (Recommended)

Add `gate_router.py` as the single supervise entry point to `ApprovalGate`, give the
roadmap-altitude decision its own gate in the contract, make `prepare` and `resume`
demand an `approval_ref` that resolves to a recorded decision, and expose the ledger via
`gate-log`.

- Pros: every supervise decision point has a gate identity, a disposition, a deadline, and
  an audit record; `approval_ref` becomes verifiable; absent-file behaviour is unchanged;
  the roadmap-altitude gate keeps its own disposition instead of borrowing the per-change
  `proposal_approval` one; reuses the checkpoint sidecar and console-decision shape ri-06
  already established.
- Cons: touches the trust-posture contract (enum, template, five schema files, "eight
  gates" tests and spec text); `prepare` gains a required argument, so `test_execution.py`
  callers need an approval fixture; a second in-flight change
  (`add-supervisor-candidate-work-digest`, unstarted) rewrites the `cycle` §2–§5 region
  of `skills/supervise/SKILL.md` (it leaves `cycle_state.py` untouched) and must be
  rebased after this lands.
- Effort: M

### Approach 3: Reuse `proposal_approval` at roadmap altitude

Same router and provenance as Approach 2, but evaluate the roadmap-approval decision as
`Gate.PROPOSAL_APPROVAL` with `context.altitude = "roadmap"` instead of adding an enum
member.

- Pros: no contract, template, or schema growth; the eight-gate tests stay green.
- Cons: one posture entry would govern two different questions (approve one change's
  proposal vs. authorize a DAG of items), so an operator cannot delegate per-change
  approval while keeping roadmap approval human — the exact split the supervise design
  argues for; `pending_gates` entries become ambiguous without inspecting context;
  autopilot's `test_gate_call_sites` invariant ("exactly one call site per autopilot
  gate") would need a carve-out.
- Effort: M

### Recommended

Approach 2. Approach 1 fails acceptance outcome 3 and leaves the most-hit gate outside the
posture. Approach 3 saves a handful of enum edits at the cost of conflating two decisions
the operator needs to set independently. The contract growth in Approach 2 is mechanical
(enum, template, five schema files, two tests, spec text — all enumerated in `tasks.md`)
and is the honest cost of turning the last prose gate into policy.

### Selected Approach

Approach 2, selected under the roadmap's standing approval: ri-04 is `approved` in
`roadmap.yaml` and the operator's instruction for this run was "start with ri-04". Per the
supervise contract, roadmap-altitude approval is inherited for every dependency-ready item
without per-item direction or plan questions, so Gate 1 was not re-asked. No modifications
requested.

## Impact

**Specs (delta files under `specs/`):**
- `supervise` — MODIFIED: Supervisor Rehydration Record (nine gate values, `decision_id`
  on pending gates); Approved Roadmap Execution (approval is a `roadmap_approval` decision
  and `prepare` refuses without it); Background Worktree Isolation (parked child resolved
  through the router). ADDED: Supervise Gate Routing.
- `roadmap-orchestration` — MODIFIED: Outcome-Only Resume Contract (parked metadata
  consumed by the router); Durable Delegated Attempt Ledger (`approval_ref` must resolve
  to a recorded decision).
- `skill-workflow` — ADDED: Roadmap Approval Gate (ninth contract gate; template and
  schema parity; prose-free enforcement extended to `skills/supervise/SKILL.md`). MODIFIED:
  Autopilot Gate Call Sites (extends the non-autopilot carve-out to `roadmap_approval`,
  matching `replan_required`, and de-numbers the all-auto scenario so it does not read
  "eight gates" once a ninth exists).

**Code:**
- `skills/shared/trust_posture.py` (enum), `TRUST_POSTURE.template.md`,
  `skills/shared/approval_gate.py` (public `console_decision` and
  `build_gate_decision_record` helpers, `ApprovalGate.check_filed`),
  `skills/shared/tests/test_trust_posture.py` and `test_approval_gate.py` (eight → nine;
  helper coverage).
- `openspec/schemas/trust-posture.schema.json`, `gate-decision.schema.json`,
  `gate-request.schema.json`, `supervisor-record.schema.json`,
  `supervisor-record-mirror.schema.json` (the last three embed the gate enum literally).
- `skills/supervise/scripts/gate_router.py` (new), `execution.py` (`prepare` approval
  argument, `resume` provenance check), `cycle_state.py` (enum imports; `gate-check`,
  `gate-answer`, `gate-log` subcommands), `skills/supervise/SKILL.md`.
- `skills/autopilot/scripts/runner.py` (delegate `_console_decision` to the shared
  helper), `skills/autopilot/scripts/autopilot.py` (delegate `build_gate_decision_record`
  to the shared helper; call sites unchanged), `skills/autopilot-roadmap/SKILL.md` (record
  the direct-invocation approval). The roadmap orchestrator's private
  `_gate_decision_record` is left as-is (out of scope; it already writes the same shape).
- Tests: `skills/tests/supervise/test_gate_router.py`, `test_gate_router_e2e.py`,
  `test_prose_free_gates.py` (new); `test_execution.py`, `test_execution_contract.py`,
  `test_cycle_state.py`, `test_supervisor_record_schema.py`, `test_workflow_contract.py`
  (updated — it pins `### Approval gate` / `### Reconcile and resume` headings and the
  phrase ``durable `approval_ref` ``); `skills/tests/autopilot/test_gate_schemas.py`,
  `test_gate_call_sites.py`, `test_console_interviewer.py` (updated).

**Rollback:** the enum addition and schema growth are additive; a posture file without a
`roadmap_approval` entry resolves to `block`. Reverting the change restores prose gates
and opaque `approval_ref` strings; no persisted state format changes except optional
fields on gate-decision records, which the schema already permits.
