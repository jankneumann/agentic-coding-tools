## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
(empty-diff)
```

### Spec excerpts
#### specs/parallel-infrastructure/spec.md
## ADDED Requirements

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after a dry invocation for that mode succeeds: the adapter's declared no-op command (for a CLI lane, `<cli> --version`; for an SDK or API lane, the adapter's own authenticated no-op such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned


#### specs/roadmap-orchestration/spec.md
## ADDED Requirements

### Requirement: Published Dispatch Contract Schemas

The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2.

#### Scenario: Existing fixtures validate against the published schemas
- **WHEN** the test suite validates every request and result fixture under `skills/tests/supervise/fixtures/execution/contracts/` and `skills/tests/autopilot-roadmap/` through `dispatch_contract.validate_request` / `validate_result`
- **THEN** every fixture named `valid-*` SHALL validate and every fixture named `invalid-*` SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer

#### Scenario: No hand-written result field set remains
- **WHEN** a guard test scans `skills/supervise/scripts/execution.py` and `skills/autopilot-roadmap/scripts/orchestrator.py`
- **THEN** neither file SHALL define `_RESULT_REQUIRED`, `_RESULT_ALLOWED`, `_validate_result`, or `_validate_dispatch_result`
- **AND** `checkpoint.schema.json`'s attempt `result` property SHALL be a `$ref` to `dispatch-result.schema.json`

#### Scenario: Schema mirrors stay identical
- **WHEN** the parity test compares `openspec/schemas/dispatch-*.schema.json` and `checkpoint.schema.json` with their `install_assets` copies
- **THEN** the bytes SHALL be identical, and a difference SHALL fail the test naming the file

#### Scenario: A version-1 result is upgraded, not rejected
- **WHEN** `ExecutionAdapter.apply` receives a schema-valid version-1 `success` result whose absolute `worktree_path` lies inside the current host's managed worktree root
- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a repo-relative `worktree_ref`, and the current `host_id`, and applied

#### Scenario: A version-1 result that cannot be made portable is rejected
- **WHEN** a version-1 result's `worktree_path` lies outside both the managed worktree root and the repo root
- **THEN** validation SHALL fail with `DispatchContractError("v1 result worktree_path is not repo-relative")` and the attempt SHALL be left unchanged

### Requirement: Launch Token Digest

The roadmap checkpoint SHALL store, for each delegated attempt, `launch_digest` with the form `sha256:<64 lowercase hex>` and SHALL NOT store a raw launch token in any field. The raw token SHALL appear only in the request returned to the host. `ExecutionAdapter.child_start` SHALL verify a presented token by constant-time comparison of its SHA-256 digest with `launch_digest`. A token SHALL be minted per launch generation: `ExecutionAdapter.resume` and `ExecutionAdapter.reissue` SHALL mint a fresh token and replace `launch_digest` under the same compare-and-swap that changes the generation. `reissue` SHALL be refused for any attempt that is not `prepared` and not a pre-go expired claim. Loading a checkpoint whose attempt carries a legacy `launch_token` SHALL convert it to `launch_digest` in memory, and the next save SHALL drop the raw value.

#### Scenario: No raw token is persisted
- **WHEN** `prepare_delegated_batch` persists a batch and the checkpoint is read back from disk
- **THEN** no attempt SHALL contain a `launch_token` field, every attempt SHALL contain a `launch_digest` matching `^sha256:[0-9a-f]{64}$`, and the token in each returned request SHALL hash to its attempt's digest

#### Scenario: child_start rejects a wrong token
- **WHEN** `child_start` is called with a token whose digest differs from `launch_digest`
- **THEN** it SHALL raise `ExecutionStateError("launch token mismatch")` and the checkpoint SHALL be byte-identical before and after the call

#### Scenario: Resume rotates the token
- **WHEN** an authorized parked attempt is resumed
- **THEN** the returned continuation request SHALL carry a token different from the previous generation's, `launch_digest` SHALL equal its digest, and `child_start` with the previous token SHALL raise `launch token mismatch`

#### Scenario: Reissue is refused after go
- **WHEN** `reissue` is called for an attempt whose launch gate has released go
- **THEN** it SHALL raise `ExecutionStateError` and SHALL NOT change `launch_digest` or the generation

#### Scenario: Legacy checkpoint loads and migrates
- **WHEN** the archived `openspec/roadmaps/archive/2026-09-26-roadmap-supervisor-orchestration/checkpoint.json` (raw tokens, absolute paths) is copied to a temp workspace, loaded, and saved
- **THEN** load SHALL succeed, and the saved file SHALL contain `launch_digest` values equal to the SHA-256 of the former tokens and no `launch_token` field

#### Scenario: A committed checkpoint with live attempts passes the default secret scan
- **WHEN** the fixture `skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`, produced by `prepare` plus `child_start` and `acknowledge`, is scanned by the CI gitleaks job using `.gitleaks.toml`
- **THEN** gitleaks SHALL report no finding, and `.gitleaks.toml` SHALL contain no path, regex, or commit entry referring to that fixture or to `launch_digest`
- **AND** a unit test SHALL assert that no field name in the serialized checkpoint matches the default `generic-api-key` keyword set (`access`, `auth`, `api`, `credential`, `creds`, `key`, `passw`, `secret`, `token`)

### Requirement: Host-Portable Attempt Isolation

Each delegated attempt SHALL record isolation as `{mode, worktree_ref, branch, host_id}`, where `worktree_ref` is the worktree path relative to the managed worktree root (`managed_worktree`) or to the repo root (`harness_provided` inside the repo), or `null` otherwise, and `host_id` is the non-secret identifier from `skills/shared/environment_profile.py`. Absolute worktree paths SHALL exist only in memory and SHALL NOT be persisted in the checkpoint, the request, or the result. When reconciling an attempt whose `host_id` differs from the current host, the adapter SHALL rebind it when a worktree for its branch exists under the current managed root whose `HEAD` contains the last recorded evidence commit and whose `loop-state.json` digest matches; otherwise it SHALL reinitialize it (create a managed worktree for the branch, increment the generation, mint a new token) when the attempt is `prepared`, `parked`, or pre-go; otherwise it SHALL leave the attempt subject to the existing quarantine rules. Legacy absolute `worktree_path` values SHALL be converted to `worktree_ref` on load when they lie inside the managed root or repo root, and SHALL otherwise mark the attempt `needs_rebind`.

#### Scenario: Persisted isolation has no absolute path
- **WHEN** a batch is prepared and the checkpoint is read back
- **THEN** every attempt's `isolation` SHALL have exactly the keys `mode`, `worktree_ref`, `branch`, `host_id`, and no persisted string in the attempt SHALL start with `/` or a drive letter

#### Scenario: Reconcile on another host rebinds a matching worktree
- **GIVEN** a checkpoint with a `parked` attempt committed on host A with evidence commit C
- **WHEN** host B, which has a managed worktree for the attempt's branch whose `HEAD` contains C and whose loop-state digest matches, reconciles the checkpoint
- **THEN** the attempt SHALL keep its generation, gain a `rebound` history entry, and record host B's `host_id`

#### Scenario: Reconcile on another host reinitializes when no worktree exists
- **GIVEN** the same committed checkpoint and a `prepared` attempt
- **WHEN** host B has no worktree for the branch and reconciles
- **THEN** a managed worktree SHALL be created for the branch, the generation SHALL increase by one, a new `launch_digest` SHALL be stored, and `prepare` on host B SHALL NOT skip the item

#### Scenario: A post-go attempt of unknown liveness is not rebound
- **WHEN** host B reconciles a post-go `launched` attempt from host A and the durable task handle cannot establish live or dead status
- **THEN** the attempt SHALL become `quarantined` and no worktree SHALL be created

#### Scenario: Rebind refuses a diverged worktree
- **WHEN** host B's worktree for the branch does not contain the evidence commit, or its loop-state digest differs
- **THEN** the attempt SHALL NOT be rebound and reconciliation SHALL report `rebind_refused:evidence_mismatch` for it

## MODIFIED Requirements

### Requirement: Outcome-Only Resume Contract

The roadmap orchestrator SHALL persist only structured dispatch outcomes and handoff identifiers needed to resume; it MUST NOT persist a child transcript in roadmap state or dispatch context.

#### Scenario: Apply a successful child outcome
- **WHEN** a child returns a schema-valid success result correlated to the current dispatch identifier and change identifier
- **THEN** the item is completed and its learning entry is written once only after the result's `worktree_ref`, `branch`, `host_id`, and loop-state evidence exactly match the prepared attempt and the worktree resolved from `worktree_ref` on the current host remains contained by its verified root
- **AND** contradictory status/outcome pairs are schema-invalid and the checkpoint records bounded outcome metadata, including the result's `degradations`, without transcript content

#### Scenario: Reject stale or mismatched child outcome
- **WHEN** a result carries a different dispatch identifier, change identifier, or already-applied attempt
- **THEN** the result is rejected without advancing the item
- **AND** a resumed run can safely redispatch or reconcile the current attempt

#### Scenario: Preserve a parked child
- **WHEN** a child Autopilot run returns a schema-valid parked result of kind `pending_gate`, `policy_pause`, `permission_blocked`, or `capability_unavailable`
- **THEN** the attempt is recorded as parked and the roadmap item is not marked failed or completed
- **AND** dependents are not failure-blocked while the parked snapshot's bounded metadata (`kind`, `reason`, and the nullable `gate`, `deadline`, `resume_hint`, plus the kind's typed payload the result contract permits — never an `approval_id`, which lives only in the supervise gate router's own ledger) remains available to that router, which is the only consumer permitted to resume it

#### Scenario: Refuse an unroutable parked result at apply time
- **WHEN** `apply` receives a parked result whose `(kind, gate)` pair has no entry in the supervisor's answer-path table
- **THEN** apply SHALL reject it with `DispatchContractError("unroutable parked result")` before any callback runs, and the attempt SHALL remain in its pre-apply state

### Requirement: Durable Delegated Attempt Ledger

The roadmap checkpoint SHALL record every delegated dispatch attempt before its request is returned to the host and SHALL preserve unresolved attempts across session restart.

#### Scenario: Persist a prepared batch before launch
- **WHEN** the scheduler prepares a safe batch of delegated item requests
- **THEN** each request's identity, exact host-portable isolation/scope/context envelope, launch digest, verified `roadmap_approval_ref`, marker path, attempt, phase, and prepared status are saved in `checkpoint.json` before the requests are emitted
- **AND** a crash after preparation loses agent launch work rather than losing the identity of potentially running work

#### Scenario: Resume with an unresolved attempt
- **WHEN** a fresh supervisor loads a checkpoint containing a prepared attempt without a correlated result
- **THEN** it reconciles a persisted

[spec excerpt truncated]


#### specs/skill-workflow/spec.md
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

Gate authority SHALL depend on whether the child is dispatched (a launch marker is returned by `dispatch_contract.read_launch_marker`). In a dispatched child the supervisor SHALL be authoritative: the child SHALL apply a gate decision only from the marker's `gate_answer` through `runner.py gate-answer --approval-ref`, SHALL NOT re-evaluate an existing `pending_gate` itself, and, when its worktree posture digest differs from the marker's `posture_digest`, SHALL NOT take an `auto` disposition for any gate but SHALL park `pending_gate` with `posture`-provenance instead. In a standalone run, `runner.py gate-check` SHALL, when a `pending_gate` has a `posture.posture_digest` different from the worktree's current posture digest, re-evaluate that gate before printing it: a `proceed` SHALL clear `pending_gate`, record a `posture`-provenance decision, apply the pending edge, and exit 3; a block SHALL replace `pending_gate` with one carrying the new digest; a gate whose last decision has `human` provenance SHALL NOT be re-evaluated. `gate-answer` SHALL record `--approval-ref gate-decision:<id>` in the decision's `provenance` and SHALL refuse (exit 2, nothing recorded) a dispatched child's reference that differs from the marker's `gate_answer.approval_ref`.

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

#### Scenario: A mismatched approval reference is refused
- **WHEN** a dispatched child runs `gate-answer --approval-ref gate-decision:X` and the marker's `gate_answer.approval_ref` is `gate-decision:Y`
- **THEN** it SHALL exit 2 and loop state SHALL be byte-identical

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase whose verified lanes from `execution_profile` are fewer than `review_requirements.min_quorum[phase]` SHALL record `park(kind=capability_unavailable, phase, missing_lanes)` and stop, and SHALL NOT run the review with a lower quorum. A standalone run (no launch marker) SHALL keep disabling CLI review below quorum and SHALL record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one lane reviewed.

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL return `parked/capability_unavailable`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one `review_skipped` entry for `PLAN_REVIEW`


#### specs/supervise/spec.md
## ADDED Requirements

### Requirement: Dispatch Result Closure

For every `(outcome class, parked.kind, parked.gate)` combination that `dispatch-result.schema.json` permits, the supervisor SHALL have exactly one answer or resume path, declared in a single table `gate_router.ANSWER_PATHS`. A contract test SHALL derive the permitted combinations from the schema itself (not from a hand-written list) and SHALL fail when any combination lacks an entry or an entry names a combination the schema forbids. The table SHALL include the `pending_gate` / `escalate_resume` path merged from `openspec/supervise-pending-escalate-answer`.

#### Scenario: Every permitted combination has a path
- **WHEN** the closure test enumerates the schema's `parked` `oneOf` branches and their `kind` / `gate` enums, plus the `success`, `failed:*`, and `vendor_limit:*` outcome classes
- **THEN** each combination SHALL map to an entry in `ANSWER_PATHS`, and the test SHALL report the full list of missing combinations when any is absent

#### Scenario: Adding a kind without a path fails the test
- **WHEN** a test fixture copy of the result schema adds a parked kind `example_kind` with no `ANSWER_PATHS` entry and the closure check runs against that copy
- **THEN** the check SHALL fail naming `("parked", "example_kind", null)`

#### Scenario: pending_gate with escalate_resume is answerable
- **WHEN** a child returns `parked/pending_gate` with `gate: escalate_resume`
- **THEN** `resolve_parked` SHALL evaluate `escalate_resume` for that dispatch generation and, on `proceed`, resume it

### Requirement: Typed Gate Answers With Provenance

Every gate-decision record the router writes SHALL carry `provenance`, either `{source: "posture", posture_digest}` or `{source: "human", approval_ref}`. When resolving a parked attempt, the router SHALL re-evaluate a prior `posture`-provenance block whose `posture_digest` differs from the current posture digest, and SHALL treat a `human`-provenance decision as final for its subject. A resume request SHALL carry the decision to the child only as `gate_answer: {gate, decision, approval_ref}`; the supervisor SHALL NOT write any file in a child worktree other than the launch marker.

#### Scenario: A posture-derived block clears after a posture change
- **GIVEN** an attempt parked `pending_gate/proposal_approval` whose supervisor record has `resolution: posture_block` and `provenance.posture_digest` D1
- **WHEN** the operator changes `TRUST_POSTURE.md` so `proposal_approval` is `auto` (digest D2) and `resolve_parked` runs for the attempt, whose persisted `roadmap_approval_ref` was verified at prepare
- **THEN** a new `proceed` record with `provenance: {source: posture, posture_digest: D2}` SHALL be written and the attempt SHALL be resumed with `gate_answer.decision: approved`
- **AND** the child applying that answer SHALL leave `PLAN` without parking again

#### Scenario: A human rejection survives a posture change
- **GIVEN** a prior record for the same subject with `resolution: console_rejected` and `provenance.source: human`
- **WHEN** the posture changes the gate to `auto` and `resolve_parked` runs
- **THEN** no new record SHALL be written, the attempt SHALL stay parked, and the router SHALL return the existing blocked entry

#### Scenario: An unchanged posture does not re-evaluate
- **WHEN** `resolve_parked` runs for a `posture_block` record whose `posture_digest` equals the current digest
- **THEN** the prior record SHALL be reused and no approval SHALL be filed

#### Scenario: A prose-only posture edit is not a posture change
- **WHEN** only the Markdown body of `TRUST_POSTURE.md` changes and its front matter is unchanged
- **THEN** the posture digest SHALL be unchanged

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve an `execution_profile` (verified lanes per mode `review`, `alternative`, `quick`; `location`; isolation mode; and `probe_command`, the only probe a worker may run) by invoking `review_dispatcher.py --check-vendors --json`, and `review_requirements` (`min_quorum` per review phase, default 2 and overridable by router context `review_min_quorum`, and `counting_lanes` ordered by the `cost_policy.tiers` ladder of `agent-coordinator/routing.yaml`), and SHALL place both in every request. The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's `degradations` on the checkpoint attempt and SHALL return them in its summary.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty `execution_profile.lanes.review`, `execution_profile.probe_command`, and `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL list only the verified lanes, so the child parks `capability_unavailable` at its first review phase

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value SHALL both contain that entry unchanged

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key variables for vendor discovery

### Requirement: Single Escalation Per Capability Park

The router SHALL map `permission_blocked` and `capability_unavailable` parks to an `escalate_resume` subject keyed by a dedupe fingerprint — `sha256(tool, rule, classifier_reason)` for `permission_blocked`, `sha256(phase, sorted(missing_lanes))` for `capability_unavailable` — and SHALL project exactly one `pending_gates` entry per fingerprint listing every parked dispatch that shares it. One `proceed` answer SHALL resume each listed attempt through its own generation-checked compare-and-swap. The stored redacted command SHALL be the output of `sanitize_session_log.sanitize()` (secret-pattern and high-entropy redaction) truncated to 256 characters.

#### Scenario: Three workers blocked on one rule produce one escalation
- **WHEN** three attempts park `permission_blocked` with tool `Bash`, rule `Bash(env *)`, and the same classifier reason
- **THEN** the supervisor record SHALL contain one `pending_gates` entry whose dispatch list has all three IDs

#### Scenario: One answer resumes every attempt in the entry
- **WHEN** the operator answers that entry `approved`
- **THEN** each of the three attempts SHALL be resumed once with a distinct new generation, and an attempt whose generation changed since projection SHALL be skipped and reported, not resumed

#### Scenario: Different missing lanes are separate escalations
- **WHEN** one attempt parks `capability_unavailable` missing `{codex}` and another missing `{codex, gemini}` for the same phase
- **THEN** two `pending_gates` entries SHALL exist

#### Scenario: A secret in the blocked command is redacted
- **WHEN** a `permission_blocked` park reports command `curl -H "Authorization: Bearer abc123..."`
- **THEN** the persisted command SHALL not contain `abc123` and SHALL contain a `[REDACTED:` marker


#### specs/trust-posture/spec.md
## ADDED Requirements

### Requirement: Roadmap-Approval-Scoped Auto Dispositions

The trust posture SHALL let the `proposal_approval` and `replan_required` gate configs declare an optional `unscoped` sub-config (`disposition` of `notify_with_timeout` or `block`, with the same `timeout_seconds` / `default_action` rules as a gate config), defaulting to `{disposition: block}` when absent. When either gate's disposition is `auto`, the approval gate SHALL apply `auto` only if the current launch marker, obtained by the gate through its `marker_reader` seam, carries a `roadmap_approval_ref`, and SHALL ignore any `roadmap_approval_ref` supplied in the evaluation context; otherwise it SHALL apply the `unscoped` config and record `scope: unscoped` and a reason naming the fallback in the decision. `unscoped` with disposition `auto`, or on any other gate, SHALL be a validation error. The loader SHALL also expose `posture_digest(posture)`: the SHA-256 of the canonical JSON of the parsed `gates` map, with a fixed value for the absent-posture default.

#### Scenario: Dispatched run with a valid approval reference proceeds
- **WHEN** `proposal_approval` is `auto` and `marker_reader` returns a marker carrying `roadmap_approval_ref`
- **THEN** the decision SHALL be `proceed` with `resolution: auto` and `scope: roadmap_approval`

#### Scenario: Standalone run falls back to the unscoped disposition
- **WHEN** `proposal_approval` is `auto`, no `unscoped` is declared, and `marker_reader` returns None
- **THEN** the decision SHALL be `blocked` with `resolution: posture_block`, `scope: unscoped`, and a reason containing `unscoped fallback`

#### Scenario: Declared notify fallback is used
- **WHEN** `replan_required` is `auto` with `unscoped: {disposition: notify_with_timeout, timeout_seconds: 600, default_action: block}` and no reference is present
- **THEN** the approval gate SHALL file an approval and apply `block` on timeout

#### Scenario: A reference not from the launch marker is ignored
- **WHEN** the evaluation context carries `roadmap_approval_ref: gate-decision:Z` but `marker_reader` returns None
- **THEN** the unscoped fallback SHALL apply and the record's `scope` SHALL be `unscoped`

#### Scenario: Invalid unscoped config is rejected
- **WHEN** `TRUST_POSTURE.md` declares `unscoped: {disposition: auto}` or declares `unscoped` on `merge`
- **THEN** `validate_posture_file` SHALL return an error naming the gate and field

#### Scenario: Digest ignores prose and key order
- **WHEN** two posture files differ only in Markdown body text and front-matter key order
- **THEN** `posture_digest` SHALL return the same value for both


### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.