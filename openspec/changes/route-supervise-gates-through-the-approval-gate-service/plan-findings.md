# Plan Findings: route-supervise-gates-through-the-approval-gate-service

Findings from `/iterate-on-plan` (threshold: medium, max 3 iterations). Each iteration
lists what was found against the code on the branch and what changed in the plan.

## Iteration 1 (2026-09-03)

Baseline: `openspec validate --strict` green; every MODIFIED requirement carries all
scenarios of the live spec (checked by script against `openspec/specs/`).

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency / feasibility | high | `ApprovalGate.evaluate` is synchronous: under `notify_with_timeout` it files, notifies, polls until `timeout_seconds`, then applies the default action — it never returns "pending". The child's `pending_gate` snapshot (`build_gate_request`) is built only for `posture_block` and never carries an `approval_id`. Design D4 step 2 and the "never re-files while pending" scenario assumed a pending state that does not exist. | Rewrote D4 as a prior-record rule over the router's own ledger (reuse `proceed`; re-surface an open `posture_block`; check a filed `approval_id` through a new `ApprovalGate.check_filed` before re-filing; `rejected` is terminal); rewrote the notify scenario as "waits for the posture timeout and honours a late answer without re-filing"; recorded the two gate-service facts in design Context. |
| 2 | completeness | high | `openspec/schemas/gate-request.schema.json` embeds the gate enum and `test_gate_schemas.py::test_gate_enum_matches_trust_posture` pins it (and `gate-decision`) to `Gate`; adding the ninth member without it goes red in CI. The mirror schema also embeds the enum (the plan left this as an open question). | Five gate-bearing schemas named everywhere (proposal, D1, tasks 1.1/1.3, skill-workflow requirement + scenario 1, contracts README, wp-contracts locks/scope); added `gate-request` and mirror copies under `contracts/schemas/`. |
| 3 | consistency | high | `build_gate_decision_record` lives in `skills/autopilot/scripts/autopilot.py` (the orchestrator has its own `_gate_decision_record`); D2 cited it as if shared, and supervise must not import the 1,700-line autopilot loop. | Moved into `shared.approval_gate` in wp-contracts (autopilot delegates; orchestrator left as-is, out of scope); `autopilot.py` added to Impact, task 1.5, wp-contracts locks/scope; AST test also forbids `import autopilot` under `skills/supervise/scripts/`. |
| 4 | clarity | high | `console_decision(gate, posture, approved, note)` was undefined against `runner._console_decision(gate, pending, …)`, which reads `pending["posture"]`; and task 3.3 ran `gate-answer` with no prior `gate-check`, which `runner.py gate-answer` semantics would refuse. | Defined `posture` as the `{disposition, posture_present}` snapshot; D5 now states that `roadmap_approval` is the one gate whose console answer may originate a record (live-posture snapshot) and every other gate needs a parked record; new scenario 5. |
| 5 | assumptions | high | Whether an approved roadmap is re-asked on every cycle (or expires) was an open question; re-asking is the interruption ri-04 exists to remove. | Decided in D5: a `proceed` record is reused while the roadmap's DAG fingerprint (sha256 of sorted `(item_id, change_id, depends_on)`) is unchanged; item completion does not re-ask, `refine-roadmap`/replan does; no time expiry. New scenario 4 and tests in 2.1/2.2. |
| 6 | consistency | medium | Proposal/design said `add-supervisor-candidate-work-digest` edits `cycle_state.py`; its proposal states `cycle_state.py` keeps its current surface — only `SKILL.md` `cycle` §2–§5 overlaps. | Corrected in proposal Approach 2, design Constraints and Risks, task 3.4. |
| 7 | testability / parallelizability | medium | `skills/tests/supervise/test_workflow_contract.py` slices `SKILL.md` on `### Approval gate` / `### Reconcile and resume` and pins ``durable `approval_ref` ``; task 3.2 could break it and wp-skill-docs could not edit it. | Task 3.2 keeps the headings and phrase (or updates the test); file added to task 3.2, wp-skill-docs scope and verification. |
| 8 | scope | medium | Task 1.4 named a non-existent `skills/autopilot/tests/test_runner_gates.py`; the runner console tests are `skills/tests/autopilot/test_console_interviewer.py`, outside wp-contracts scope. | Task and wp-contracts scope/verification corrected. |
| 9 | parallelizability | medium | wp-router edits `supervised-dispatch-request.schema.json` (task 2.6) without locking it; wp-contracts locks omitted the template, `gate-request`, mirror and `autopilot.py`. | Locks added. |
| 10 | clarity | medium | `gate-log` "active changes" and `gate-check` exit-4 semantics were undefined. | D6: the change_ids named by the roadmap's items, tagged with `origin`; D5: exit 4 = terminal block (`rejected` / `timeout_default_block` / `coordinator_unreachable`), operator may still `gate-answer`. |
| 11 | security | low | `require_approval_ref` trusts the tracked ledger, so repository write access can forge a `proceed` record. | Documented in D3 and Risks as the same trust boundary `TRUST_POSTURE.md` sits on; no signing (out of scope). |
| 12 | clarity | low | `approval_ref` pattern differed between D3 (`[0-9a-f-]{36}`) and the contract patch (8-4-4-4-12). | D3 aligned to the patch. |

Deferred / out of scope:
- The roadmap orchestrator's private `_gate_decision_record` duplicates the shared builder; consolidating it is a follow-up, not part of ri-04.
- `BridgeCoordinatorClient.push_notification` always returning `False` (ri-05) still fails a `default_action: proceed` closed; documented, unchanged.

## Iteration 2 (2026-09-03)

Re-review of the iteration-1 documents against `cycle_state.py` and the `cycle` SKILL flow.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 13 | completeness | high | `pending_gates` and `standing_decisions` are non-derivable sections that `build_supervisor_record` only carries forward; nothing deterministic adds or clears an entry, so the router's blocked decisions would never reach a rehydrated session and answered gates would never leave the digest. | New D7: the router projects blocked decisions into the tracked mirror's `pending_gates` (keyed by `decision_id`) and proceeds out of it, upserting the `roadmap_approval` standing decision, through the existing `cycle_state.write_mirror`; requirement sentence and scenario 11 added; tasks 2.1/2.2 cover it. |
| 14 | consistency | high | The `cycle` SKILL's final step rebuilds the record from the pre-gate `$SUPERVISE_RECORD` snapshot and writes the mirror, which would overwrite the router's projection made at the gate. | D7 and task 3.2: re-select the prior with `rehydrate --handoff` at write time; e2e test rehydrates after the gate and after the final write. |
| 15 | clarity | medium | `execute` had no deterministic source for `roadmap_approval_ref` in a rehydrated session. | D5: `execute` always opens with `gate-check`; its exit-3 record supplies the ref; exit 0/4 is the refuse path. |
| 16 | clarity | medium | `cycle --dry-run` writes no supervisor state, but `gate-check` appends to `checkpoint.json` and the mirror. | D5: `gate-check` never runs under `--dry-run`; task 2.7 asserts the subcommand has no dry-run mode to hide behind; task 3.2 documents it. |
| 17 | feasibility | low | Checked that `openspec/roadmaps/` and `openspec/supervise/` are inside `_ALLOWED_WRITE_PREFIXES`, so the router's checkpoint and mirror writes pass `audit-since`; the fingerprint excludes the mirror, so a projection never forces a re-sense. | Recorded in D7; no change needed. |

Remaining below threshold: none identified. Parallelizability unchanged
(wp-contracts → wp-router ∥ wp-skill-docs → wp-integration; max width 2 packages, 3 task
chains inside wp-router after 2.2).
