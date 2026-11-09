## ADDED Requirements

### Requirement: Code-Emitted Dispatch Result

`skills/autopilot/scripts/runner.py` SHALL provide `emit-result <change-id> --dispatch-id ID --generation N --attempt A` that derives a `dispatch-result.schema.json` version-2 result from the committed `loop-state.json` through `dispatch_contract.result_from_loop_state`, writes it to `openspec/changes/<change-id>/dispatch-results/<dispatch-slug>-g<N>.json` (where `dispatch-slug` replaces each character outside `[A-Za-z0-9._-]` with `-`), and prints it to stdout. The mapping SHALL be, first match wins: `park` set -> `parked/<park.kind>`; `pending_gate` set -> `parked/pending_gate` with the pending gate; `ESCALATE` -> `parked/policy_pause` with `previous_phase` in `resume_hint`; `DONE` with `goal_gate.verdict` `abandoned` -> `failed:abandoned`; `DONE` with verdict `passed` and a `last_handoff_id` -> `success`; any other `DONE` -> `failed:goal_gate_unverified`. Evidence SHALL be the loop-state path, the `HEAD` commit, and the SHA-256 of `loop-state.json` at `HEAD`. Worker prompts and SKILL.md files SHALL instruct workers to return only the path and commit of this file, never a hand-composed result.

#### Scenario: Every terminal and parked shape maps to a schema-valid result
- **WHEN** the end-to-end test builds a committed loop state for each of: `DONE`/passed, `DONE`/abandoned, `DONE`/refused, `ESCALATE`, `pending_gate` for each gate the result schema permits, `park` of kind `permission_blocked`, and `park` of kind `capability_unavailable`, and runs `emit-result` for each
- **THEN** each written file SHALL validate against `dispatch-result.schema.json`, its outcome and kind SHALL equal the mapping above, and `ExecutionAdapter.apply` SHALL accept it for a matching prepared attempt

#### Scenario: A non-terminal phase produces no result
- **WHEN** `emit-result` runs while `current_phase` is `IMPLEMENT` with no `pending_gate` or `park`
- **THEN** it SHALL exit 5, write no file, and print `runner: loop state is not terminal or parked`

#### Scenario: Uncommitted loop state is refused
- **WHEN** `loop-state.json` differs from its `HEAD` version
- **THEN** `emit-result` SHALL exit 2 and write no file

#### Scenario: Abandoned work is not reported as success
- **WHEN** the loop reached `DONE` through `ESCALATE --abandoned-->`
- **THEN** the result outcome SHALL be `failed:abandoned`

### Requirement: Loop State Parks and Degradations

`LoopState` SHALL advance to `schema_version` 6, adding `park: dict | None` and `degradations: list[dict]`, and `load_state()` SHALL migrate a version-5 file by defaulting both. `runner.py park <change-id> --kind permission_blocked --tool T --rule R --command C --reason X` and `runner.py park <change-id> --kind capability_unavailable --phase P --missing-lane L ...` SHALL be the only writers of `park`; `runner.py record-degradation <change-id> --code CODE --phase P --detail D` SHALL be the only writer of `degradations`, accepting only the enumerated codes of `dispatch-result.schema.json`. `_apply_transition` SHALL refuse to move a phase while `park` is set, and `runner.py gate-answer --gate escalate_resume --approval-ref R` SHALL clear it.

#### Scenario: Version-5 state migrates
- **WHEN** `load_state()` reads a `schema_version` 5 file
- **THEN** the result SHALL have `schema_version` 6, `park` None, `degradations` [], and every v5 field unchanged

#### Scenario: A park blocks transitions
- **WHEN** `park` is set and `runner.py apply-outcome` is called
- **THEN** it SHALL exit non-zero naming the park kind, and `current_phase` SHALL be unchanged

#### Scenario: An unknown degradation code is rejected
- **WHEN** `record-degradation` is called with `--code made_up`
- **THEN** it SHALL exit 2 and `degradations` SHALL be unchanged

#### Scenario: The park command is redacted before it is stored
- **WHEN** `park --kind permission_blocked --command 'curl -H "Authorization: Bearer abc123def456ghi789"'` runs
- **THEN** the stored `park.command` SHALL not contain `abc123def456ghi789`

### Requirement: Gate Authority and Re-Evaluation on Resume

Gate authority SHALL depend on whether the child is dispatched (a launch marker is returned by `dispatch_contract.read_launch_marker`). In a dispatched child the supervisor SHALL be authoritative: the child SHALL apply a gate decision only from the marker's `gate_answer` through `runner.py gate-answer --approval-ref`, SHALL NOT re-evaluate an existing `pending_gate` itself, and, when its worktree posture digest differs from the marker's `posture_digest`, SHALL NOT take an `auto` disposition for any gate but SHALL park `pending_gate` with `posture`-provenance instead. In a standalone run, `runner.py gate-check` SHALL, when a `pending_gate` has a `posture.posture_digest` different from the worktree's current posture digest, re-evaluate that gate before printing it: a `proceed` SHALL clear `pending_gate`, record a `posture`-provenance decision, apply the pending edge, and exit 3; a block SHALL replace `pending_gate` with one carrying the new digest; a gate whose last decision has `human` provenance SHALL NOT be re-evaluated. A human rejection of a gate SHALL stay in force until a later `human`-provenance `proceed` on `escalate_resume` (the operator resuming the run); while it is in force, `gate-check --gate` for that gate SHALL record nothing, SHALL enter `ESCALATE` if the loop is not already there, and SHALL exit 4, and a `posture`-provenance resume SHALL NOT end it. `gate-answer` SHALL record `--approval-ref gate-decision:<id>` in the decision's `provenance` and SHALL refuse (exit 2, nothing recorded) a dispatched child's reference that differs from the marker's `gate_answer.approval_ref`.

#### Scenario: A dispatched child applies the supervisor's answer
- **GIVEN** a dispatched child parked at `pending_gate/proposal_approval` and a resumed marker whose `gate_answer` is `{gate: proposal_approval, decision: approved, approval_ref: gate-decision:Y}`
- **WHEN** the child runs `gate-answer --gate proposal_approval --decision approved --approval-ref gate-decision:Y`
- **THEN** `pending_gate` SHALL be None, the last decision SHALL carry `provenance: {source: human, approval_ref: gate-decision:Y}` or, when the supervisor's decision was posture-derived, `{source: posture, posture_digest}` copied from the answer, and the pending edge SHALL have been applied

#### Scenario: A dispatched child does not self-re-evaluate
- **WHEN** a dispatched child with a `pending_gate` and no `gate_answer` in its marker runs `gate-check` after its worktree posture changed
- **THEN** `pending_gate` SHALL be printed unchanged and exit 0, and no decision SHALL be recorded

#### Scenario: Posture drift between child and supervisor blocks auto
- **WHEN** a dispatched child's worktree posture has `proposal_approval: auto` but its digest differs from the marker's `posture_digest`
- **THEN** the gate SHALL park as `pending_gate` with reason containing `posture digest differs from dispatch`, and the child SHALL NOT proceed

#### Scenario: A standalone stale posture block clears without an answer
- **GIVEN** a standalone run with `pending_gate` for `pr_creation` recorded under posture digest D1 (gate `block`)
- **WHEN** the worktree posture changes `pr_creation` to `auto` and `gate-check` runs
- **THEN** `pending_gate` SHALL be None, the last decision SHALL have `outcome: proceed` and `provenance.source: posture`, and the exit code SHALL be 3

#### Scenario: A human rejection is not re-evaluated
- **WHEN** the last decision for the gate has `provenance.source: human` and outcome `blocked`, and the posture changes to `auto`
- **THEN** `gate-check` SHALL NOT record a new decision and the loop SHALL remain in `ESCALATE`

#### Scenario: An operator resume ends a human rejection
- **GIVEN** a human rejection of `merge` followed by a `human`-provenance `escalate_resume` `proceed`
- **WHEN** the resumed phase runs `gate-check --gate merge`
- **THEN** the gate SHALL be evaluated again under the current posture

#### Scenario: A mismatched approval reference is refused
- **WHEN** a dispatched child runs `gate-answer --approval-ref gate-decision:X` and the marker's `gate_answer.approval_ref` is `gate-decision:Y`
- **THEN** it SHALL exit 2 and loop state SHALL be byte-identical

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase whose verified lanes from `execution_profile` are fewer than `review_requirements.min_quorum[phase]` SHALL record `park(kind=capability_unavailable, phase, missing_lanes)` and stop, and SHALL NOT run the review with a lower quorum. A standalone run (no launch marker) SHALL keep disabling CLI review below quorum and SHALL record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one lane reviewed.

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL return `parked/capability_unavailable`

#### Scenario: A single-lane review under a quorum-1 policy is recorded
- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy data and exactly one review lane dispatches, the others having failed to dispatch
- **THEN** the review SHALL run and `degradations` SHALL contain a `single_vendor_review` entry for `PLAN_REVIEW` whose detail names the vendor
- **AND** the child SHALL NOT have read environment variables or credentials to decide that only one lane exists

#### Scenario: GATEKEEPER review scheduling on the host-driven path
- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one `review_skipped` entry for `PLAN_REVIEW`
