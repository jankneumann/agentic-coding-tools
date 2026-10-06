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
- **THEN** each request's identity, exact host-portable isolation/scope/context envelope, launch digest, marker path, attempt, phase, and prepared status are saved in `checkpoint.json` before the requests are emitted
- **AND** a crash after preparation loses agent launch work rather than losing the identity of potentially running work

#### Scenario: Resume with an unresolved attempt
- **WHEN** a fresh supervisor loads a checkpoint containing a prepared attempt without a correlated result
- **THEN** it reconciles a persisted host launch acknowledgement, an atomic child-start marker, and worktree Autopilot state before deciding whether work launched
- **AND** pre-go stale claims may be reclaimed by generation compare-and-swap through `reissue`, which mints a new token; after go, takeover requires positive task-death evidence, and unknown liveness becomes non-resumable quarantine

#### Scenario: Reconcile lease crash windows
- **WHEN** a crash occurs before marker creation, after marker but before Autopilot entry, before host acknowledgement, or while a child is active
- **THEN** the generation-specific ack/go barrier prevents Autopilot entry before durable handle acknowledgement, while markers, heartbeats, handle status, exact worktree loop-state, and terminal handoff/result evidence classify the generation
- **AND** a pre-go expired claim may be reclaimed safely, but a post-go generation may be reclaimed only after positive task-death evidence; mere absence or expiry enters quarantine
- **AND** duplicate owners, presentation of a superseded generation's token, and stale owners that fail compare-and-swap are refused

#### Scenario: Resume an authorized parked attempt
- **WHEN** the supervise gate router supplies an `approval_ref` of the form `gate-decision:<decision_id>` for a parked dispatch of any kind
- **THEN** the resume command verifies the reference resolves to a `gate_decisions` record in the same checkpoint with outcome `proceed`, a gate equal to the parked gate (or `escalate_resume` for `policy_pause`, `permission_blocked`, and `capability_unavailable`), and a subject matching the dispatch, then compare-and-swaps parked to prepared, increments the lease generation, mints a new launch token, and emits one continuation with the same dispatch ID, attempt, worktree reference, and loop-state, carrying a typed `gate_answer`
- **AND** a reference that does not resolve, resolves to a `blocked` decision, or names a different gate or subject is rejected without mutating the attempt
- **AND** the normal child-start protocol transitions it to launched while duplicate or unauthorized resumes are rejected
- **AND** `ExecutionAdapter.prepare` likewise requires a `roadmap_approval_ref` resolving to a `proceed` `roadmap_approval` decision for the checkpoint's roadmap before any attempt is written

#### Scenario: Quarantine unknown post-go liveness
- **WHEN** a post-go generation has no terminal result and its durable task handle cannot positively establish live or dead status
- **THEN** the attempt becomes `quarantined` with its uncertain lease unreleased and no takeover or duplicate Autopilot entry occurs
- **AND** approval-gate resume is forbidden until reconciliation positively proves the prior task dead or terminal
