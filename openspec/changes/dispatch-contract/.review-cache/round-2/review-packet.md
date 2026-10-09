## Review Round 2

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
diff --git a/openspec/changes/dispatch-contract/design.md b/openspec/changes/dispatch-contract/design.md
index 771a5cb..8090b62 100644
--- a/openspec/changes/dispatch-contract/design.md
+++ b/openspec/changes/dispatch-contract/design.md
@@ -34,8 +34,13 @@ fixtures stay byte-unchanged and must pass this way (acceptance outcome 1). A v1
 request gains an empty `execution_profile`/`review_requirements` (which the child
 treats as standalone for D10 purposes). A v1 result gains
 `degradations: []`, its absolute `worktree_path` is converted to `worktree_ref`
-against the current host's repo root, and `host_id` is set to the current host. A v1
-result whose path cannot be made repo-relative is rejected with a named error.
+against the current host's managed worktree root or repo root, its absolute
+`evidence.loop_state_path` is rewritten relative to that worktree, and `host_id` is
+set to the current host. A v1 result whose paths cannot be made relative is rejected
+with a named error. `upgrade_v1(doc, *, repo_root, managed_root, host_id)` takes the
+host context explicitly; schema validation of a v1 document (against the frozen v1
+reader schemas, D2) is host-independent, so the existing fixtures validate on any
+host and only the upgrade step is host-bound.
 
 - *Alternative:* bump in place with no v1 support. Rejected: workers already running on
   `multiplayer-collaboration` return v1 results, and refusing them would strand those
@@ -57,6 +62,33 @@ object in `checkpoint.schema.json` becomes a `$ref` to
 `dispatch-result.schema.json`, resolved through a `referencing.Registry` built from
 the schema directory.
 
+The v1 boundary is also published, but unused at runtime, as JSON Schemas under
+`openspec/contracts/roadmap-orchestration/schemas/` (`supervised-dispatch-request`,
+`supervised-dispatch-result`, `delegated-dispatch-attempt`, `bounded-dispatch-context`,
+each with an `https://agentic-coding-tools.dev/contracts/...` `$id`). They are
+validated today only by tests (`skills/tests/supervise/test_execution_contract.py`,
+`test_execution.py`, `roadmap-runtime/test_dispatch_scheduler.py`,
+`autopilot-roadmap/test_supervised_dispatch_e2e.py`). To end with one definition per
+shape:
+
+- `supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json`
+  are frozen as the **v1 reader schemas**: `upgrade_v1()` validates a v1 document
+  against them before upgrading it, and nothing writes v1. They are deleted with v1
+  reading (Open questions).
+- `delegated-dispatch-attempt.schema.json` becomes the **single attempt definition**:
+  it gains `launch_digest`, `roadmap_approval_ref` and portable isolation, and
+  `checkpoint.schema.json`'s `dispatch_attempts.items` becomes a `$ref` to it (its
+  `result` in turn `$ref`s `dispatch-result.schema.json`).
+- `bounded-dispatch-context.schema.json` is kept and `$ref`'d by the v2 request.
+- The v2 request/result live only at `openspec/schemas/dispatch-*.schema.json`.
+  `dispatch_contract`'s registry loads every schema in `openspec/schemas/` and
+  `openspec/contracts/roadmap-orchestration/schemas/` by `$id`; the four contract
+  files are mirrored under `skills/roadmap-runtime/install_assets/openspec/` at the
+  same relative paths, and the locator's install_assets fallback covers both
+  directories.
+- The four tests above validate through `dispatch_contract` instead of building their
+  own validators.
+
 - *Alternative:* generate Python validators from the schema at build time. Rejected:
   adds a build step that installed copies in consumer repos would not run.
 - *Alternative:* keep the hand validators and add a parity test. Rejected: two
@@ -251,11 +283,27 @@ an `escalate_resume` subject keyed by a *dedupe fingerprint* instead of by dispa
 - `capability_unavailable`: `sha256(phase, sorted(missing_lanes))`.
 
 N parked attempts with the same fingerprint produce one `pending_gates` entry listing
-all their dispatch IDs. One operator answer resumes every attempt in that entry, each
-through its own generation-checked CAS. The redacted command is stored only after
-passing through `skills/session-log/scripts/sanitize_session_log.sanitize()`
-(secret-pattern and high-entropy redaction), truncated to 256 characters; it is
-redacted by `runner.py park` in the child, and re-sanitized by the router.
+all their dispatch IDs, each with the `lease_generation` it had at projection. One
+operator answer resumes every attempt in that entry, each through its own
+generation-checked CAS.
+
+Decision-record shape for the fan-out: answering a fingerprint entry writes **one
+`escalate_resume` record per listed dispatch**, each with that dispatch's own
+`dispatch_id` and projected `lease_generation`, plus the shared `dedupe_fingerprint`
+and the answer's `provenance`. `gate_router.require_approval_ref` therefore keeps its
+existing per-dispatch checks (`dispatch_id` equal, and for `escalate_resume`
+`lease_generation` equal) unchanged; an attempt whose generation moved since
+projection fails that check and is skipped and reported. `ExecutionAdapter.resume`
+accepts parked kinds `permission_blocked` and `capability_unavailable` in addition to
+`pending_gate` and `policy_pause`, with expected gate `escalate_resume`, and also
+requires the record's `dedupe_fingerprint` to equal the fingerprint recomputed from
+the attempt's parked payload.
+
+The redacted command is stored only after passing through
+`skills/session-log/scripts/sanitize_session_log.sanitize()` (secret-pattern and
+high-entropy redaction; the stored value is the first element of its
+`(content, redactions)` return value), truncated to 256 characters; it is redacted by
+`runner.py park` in the child, and re-sanitized by the router.
 
 ### D10. Execution profile and honest quorum
 
@@ -267,10 +315,14 @@ inside the adapter's existing credential path and never printed; workers never p
 `probe_command`, the only probe a worker may re-run. `review_requirements` holds
 `min_quorum` per review phase (`PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW`; default 2,
 today's `--min-vendors` value, overridable by router context key `review_min_quorum`)
-and `counting_lanes`: verified lanes ordered by the `cost_policy.tiers` ladder in
+and `counting_lanes`: every lane the roster (`agents.yaml`) configures for mode
+`review`, **verified or not**, ordered by the `cost_policy.tiers` ladder in
 `agent-coordinator/routing.yaml` (subscription-local, subscription-cloud, metered-api).
-The ladder orders lanes; it does not exclude any tier from counting. `routing.yaml`
-itself is not edited.
+`execution_profile.lanes.review` holds the verified subset, so a park's
+`missing_lanes` is `counting_lanes` minus the verified lanes and is non-empty
+whenever quorum is unmet by a configured-but-unverified lane; distinct gaps therefore
+fingerprint differently (D9). The ladder orders lanes; it does not exclude any tier
+from counting. `routing.yaml` itself is not edited.
 
 In a dispatched child (launch marker present), a review phase whose verified lanes are
 fewer than `review_requirements.min_quorum[phase]` records
@@ -278,6 +330,19 @@ fewer than `review_requirements.min_quorum[phase]` records
 standalone run keeps today's behaviour (disable CLI review) but appends a
 `single_vendor_review` or `review_skipped` degradation.
 
+Where this happens: today the below-quorum decision is made in the worker protocol
+(`skills/autopilot/SKILL.md` runs `--check-vendors` and sets
+`CLI_REVIEW_ENABLED=false`, so the review phases are skipped and `converge()` never
+runs). In a dispatched child the protocol instead keeps review enabled and, at
+`PLAN_REVIEW` / `IMPL_REVIEW` entry, compares `execution_profile.lanes.review` with
+`review_requirements.min_quorum[phase]` and runs `runner.py park --kind
+capability_unavailable`. A standalone run below quorum runs `runner.py
+record-degradation --code review_skipped` when it disables review.
+`convergence_loop.converge()` gains a pre-dispatch guard that returns
+`reason="capability_unavailable"` when handed fewer verified lanes than `min_quorum`;
+it never writes loop state (`runner.py` stays the only writer of `park` and
+`degradations`, D11).
+
 Degradation codes (closed enum): `single_vendor_review`, `review_skipped`,
 `coordinator_projection_forbidden`, `audit_sink_failed`, `phase_fallback_inline`,
 `handoff_local_fallback`. Each entry is `{code, phase, detail<=512}`, at most 32 per
diff --git a/openspec/changes/dispatch-contract/proposal.md b/openspec/changes/dispatch-contract/proposal.md
index 7daa450..c308f28 100644
--- a/openspec/changes/dispatch-contract/proposal.md
+++ b/openspec/changes/dispatch-contract/proposal.md
@@ -9,11 +9,14 @@
 
 The first `/supervise execute` run of `multiplayer-collaboration` (2026-10-05/06)
 dispatched four workers (ri-01, ri-02, ri-05, ri-20) and none reached
-implementation. Every stall traced to the supervisor-worker boundary, which has no
-published contract: the dispatch request and result exist only as three hand-kept
-validators (`execution.py` `_validate_result`, `orchestrator.py`
-`_validate_dispatch_result`, and an inline copy inside `checkpoint.schema.json`) plus
-test fixtures. Each worker prompt restated the result shape by hand, and every
+implementation. Every stall traced to the supervisor-worker boundary, whose published
+contract is not the one the runtime enforces: v1 JSON Schemas exist under
+`openspec/contracts/roadmap-orchestration/schemas/` (`supervised-dispatch-request`,
+`supervised-dispatch-result`, `delegated-dispatch-attempt`,
+`bounded-dispatch-context`), but only tests validate against them. At runtime the
+request and result are checked by three hand-kept validators (`execution.py`
+`_validate_result`, `orchestrator.py` `_validate_dispatch_result`, and an inline copy
+inside `checkpoint.schema.json`), none of which reads those schemas. Each worker prompt restated the result shape by hand, and every
 behaviour the prompt left out was decided by the worker. The observed failures:
 
 1. A gate parked under a missing posture stayed parked after the operator adopted a
@@ -42,7 +45,10 @@ first.
 
 - **Published schemas.** Add `openspec/schemas/dispatch-request.schema.json` and
   `dispatch-result.schema.json` (`schema_version` 2) as the only definition of the
-  boundary. A new `skills/shared/dispatch_contract.py` loads and validates them;
+  boundary. The existing v1 contract schemas are frozen as v1 reader schemas
+  (request, result), become the single attempt definition `$ref`'d by
+  `checkpoint.schema.json` (attempt), or are `$ref`'d by the v2 request (context)
+  (design D2). A new `skills/shared/dispatch_contract.py` loads and validates them;
   `execution.py`, `orchestrator.py` and `checkpoint.schema.json` (via `$ref`) consume
   that single definition, and their hand-written field sets are deleted. Version-1
   documents remain readable (D1).
@@ -142,6 +148,10 @@ Affected code:
   edited `checkpoint.schema.json`, `gate-decision.schema.json`,
   `gate-request.schema.json`, `trust-posture.schema.json`; mirrors in
   `skills/roadmap-runtime/install_assets/openspec/schemas/`.
+- `openspec/contracts/roadmap-orchestration/schemas/`: `delegated-dispatch-attempt`
+  edited (digest, portable isolation); `supervised-dispatch-request`/`-result` frozen
+  as v1 reader schemas; all four mirrored under `install_assets`.
+- `skills/shared/environment_profile.py` (`host_id()`).
 - `skills/shared/`: new `dispatch_contract.py`; `trust_posture.py` (digest, `unscoped`
   fallback), `approval_gate.py` (provenance, scoped auto).
 - `skills/autopilot/scripts/`: `runner.py` (`emit-result`, `park`,
@@ -153,7 +163,9 @@ Affected code:
 - `skills/autopilot-roadmap/scripts/orchestrator.py` (prepare, validation via contract).
 - `skills/supervise/scripts/execution.py`, `gate_router.py`, `skills/supervise/SKILL.md`,
   `skills/autopilot/SKILL.md` (worker protocol: emit-result, park, no env probing).
-- Tests under `skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure}/`.
+- Tests under `skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure,install_sh}/`,
+  including `supervise/test_execution_contract.py` and every helper that copies
+  `checkpoint.schema.json` into a temporary repo.
 
 Compatibility: v1 results and legacy checkpoints keep loading (D1, D6, D7). Loop
 state moves to `schema_version` 6 with defaulted new fields. In-flight workers on
diff --git a/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md b/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
index f508135..588ab06 100644
--- a/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
+++ b/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
@@ -2,11 +2,11 @@
 
 ### Requirement: Published Dispatch Contract Schemas
 
-The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2.
+The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2. The existing `openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json` SHALL be kept unchanged as the version-1 reader schemas that a version-1 document is validated against before upgrade, `delegated-dispatch-attempt.schema.json` SHALL be the only definition of a checkpoint attempt (`checkpoint.schema.json` SHALL `$ref` it), and `bounded-dispatch-context.schema.json` SHALL be `$ref`'d by the version-2 request. Schema validation of a version-1 document SHALL be host-independent; only the upgrade step, which takes `repo_root`, `managed_root`, and `host_id` explicitly, depends on the host.
 
 #### Scenario: Existing fixtures validate against the published schemas
-- **WHEN** the test suite validates every request and result fixture under `skills/tests/supervise/fixtures/execution/contracts/` and `skills/tests/autopilot-roadmap/` through `dispatch_contract.validate_request` / `validate_result`
-- **THEN** every fixture named `valid-*` SHALL validate and every fixture named `invalid-*` SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer
+- **WHEN** the test suite validates the byte-unchanged fixtures under `skills/tests/supervise/fixtures/execution/contracts/` with this mapping: `valid-request.json` and `invalid-continuation-without-kind.json` through `dispatch_contract.validate_request`; each entry (`success`, `parked`) of `valid-results.json` through `dispatch_contract.validate_result`; `valid-prepared-attempt.json` through the checkpoint attempt validator after the legacy reader converts its `launch_token`
+- **THEN** every `valid-*` document SHALL validate and every `invalid-*` document SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer, on any host and without a managed worktree root existing at the fixtures' `/workspace/...` paths
 
 #### Scenario: No hand-written result field set remains
 - **WHEN** a guard test scans `skills/supervise/scripts/execution.py` and `skills/autopilot-roadmap/scripts/orchestrator.py`
@@ -19,7 +19,7 @@ The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and
 
 #### Scenario: A version-1 result is upgraded, not rejected
 - **WHEN** `ExecutionAdapter.apply` receives a schema-valid version-1 `success` result whose absolute `worktree_path` lies inside the current host's managed worktree root
-- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a repo-relative `worktree_ref`, and the current `host_id`, and applied
+- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a relative `worktree_ref`, an `evidence.loop_state_path` relative to that worktree, and the current `host_id`, and applied
 
 #### Scenario: A version-1 result that cannot be made portable is rejected
 - **WHEN** a version-1 result's `worktree_path` lies outside both the managed worktree root and the repo root
@@ -127,8 +127,8 @@ The roadmap checkpoint SHALL record every delegated dispatch attempt before its
 
 #### Scenario: Resume an authorized parked attempt
 - **WHEN** the supervise gate router supplies an `approval_ref` of the form `gate-decision:<decision_id>` for a parked dispatch of any kind
-- **THEN** the resume command verifies the reference resolves to a `gate_decisions` record in the same checkpoint with outcome `proceed`, a gate equal to the parked gate (or `escalate_resume` for `policy_pause`, `permission_blocked`, and `capability_unavailable`), and a subject matching the dispatch, then compare-and-swaps parked to prepared, increments the lease generation, mints a new launch token, and emits one continuation with the same dispatch ID, attempt, worktree reference, and loop-state, carrying a typed `gate_answer`
-- **AND** a reference that does not resolve, resolves to a `blocked` decision, or names a different gate or subject is rejected without mutating the attempt
+- **THEN** the resume command verifies the reference resolves to a `gate_decisions` record in the same checkpoint with outcome `proceed`, a gate equal to the parked gate (or `escalate_resume` for `policy_pause`, `permission_blocked`, and `capability_unavailable`), a `dispatch_id` equal to the parked dispatch, for `escalate_resume` a `lease_generation` equal to the attempt's current generation, and for `permission_blocked` and `capability_unavailable` a `dedupe_fingerprint` equal to the one recomputed from the attempt's parked payload, then compare-and-swaps parked to prepared, increments the lease generation, mints a new launch token, and emits one continuation with the same dispatch ID, attempt, worktree reference, and loop-state, carrying a typed `gate_answer`
+- **AND** a reference that does not resolve, resolves to a `blocked` decision, or names a different gate, dispatch, lease generation, or fingerprint is rejected without mutating the attempt
 - **AND** the normal child-start protocol transitions it to launched while duplicate or unauthorized resumes are rejected
 - **AND** `ExecutionAdapter.prepare` likewise requires a `roadmap_approval_ref` resolving to a `proceed` `roadmap_approval` decision for the checkpoint's roadmap before any attempt is written
 
diff --git a/openspec/changes/dispatch-contract/tasks.md b/openspec/changes/dispatch-contract/tasks.md
index 280d6be..ecea72d 100644
--- a/openspec/changes/dispatch-contract/tasks.md
+++ b/openspec/changes/dispatch-contract/tasks.md
@@ -28,8 +28,18 @@
   `launch_digest` (`^sha256:[0-9a-f]{64}$`); attempt `roadmap_approval_ref`; isolation
   `{mode, worktree_ref, branch, host_id}`; parked kinds extended; `rebound` history state. — RO Launch Token Digest,
   Host-Portable Attempt Isolation
-- [ ] 2.4 Mirror 2.1-2.3 into `skills/roadmap-runtime/install_assets/openspec/schemas/`
-  and add the byte-parity test. (dep 2.1-2.3) — RO Published Dispatch Contract Schemas
+- [ ] 2.3a Existing contract schemas (design D2): edit
+  `openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json`
+  to the new attempt shape and make `checkpoint.schema.json` `dispatch_attempts.items`
+  `$ref` it; keep `supervised-dispatch-request`/`-result.schema.json` byte-unchanged as
+  v1 reader schemas; `$ref` `bounded-dispatch-context.schema.json` from the v2
+  request. Repoint `skills/tests/supervise/test_execution_contract.py` at the v2/v1
+  schemas through a registry. (dep 2.1-2.3) — RO Published Dispatch Contract Schemas
+- [ ] 2.4 Mirror 2.1-2.3a into `skills/roadmap-runtime/install_assets/openspec/`
+  (`schemas/` and `contracts/roadmap-orchestration/schemas/`) and add the byte-parity
+  test; add the new installed paths to
+  `skills/tests/install_sh/test_openspec_assets.py`. (dep 2.1-2.3a) — RO Published
+  Dispatch Contract Schemas
 
 ## 3. Posture provenance and scope  `[wp-posture]` (no deps)
 
@@ -53,7 +63,12 @@
 - [ ] 4.2 `skills/shared/dispatch_contract.py`: schema locator with install_assets
   fallback, `validate_request`, `validate_result`, `upgrade_v1`,
   `result_from_loop_state`, `dispatch_slug`, `read_launch_marker`,
-  `DispatchContractError`. (dep 4.1)
+  `DispatchContractError`; a `referencing.Registry` built from every schema under
+  `openspec/schemas/` and `openspec/contracts/roadmap-orchestration/schemas/`
+  (`$id`-keyed) and exported as `schema_registry(repo_root)`. (dep 4.1)
+- [ ] 4.3 `skills/shared/environment_profile.py`: add `host_id()` (cloud session
+  environment ID when present, else a hash of the machine ID; never a hostname or
+  username) with a unit test. — RO Host-Portable Attempt Isolation (D7)
 
 ## 5. Runtime ledger  `[wp-runtime-ledger]` (deps: 4.2)
 
@@ -63,8 +78,16 @@
   path). Update `test_delegated_checkpoint.py` and `test_dispatch_scheduler.py`,
   which pin `launch_token` today. — RO Launch Token Digest, Host-Portable Attempt Isolation
 - [ ] 5.2 `roadmap-runtime/scripts/models.py` + `checkpoint.py`: attempt fields
-  `launch_digest` and portable isolation; legacy migration on load; `needs_rebind`.
-  (dep 5.1)
+  `launch_digest` and portable isolation; legacy migration on load; `needs_rebind`;
+  `validate_against_schema` builds its `Draft202012Validator` with
+  `dispatch_contract.schema_registry(repo_root)` so the checkpoint's `$ref`s resolve
+  (today it uses a bare validator, so `resolve_readiness.py` and checkpoint load would
+  fail on an unresolvable reference). (dep 5.1)
+- [ ] 5.2a Update every test helper that copies only `checkpoint.schema.json` into a
+  temporary repo to also copy the schemas it `$ref`s: `roadmap-runtime/test_readiness.py`,
+  `autopilot-roadmap/test_supervised_dispatch.py`, `test_supervised_dispatch_e2e.py`
+  (this package), and `supervise/test_execution.py`, `test_gate_router.py`,
+  `test_gate_router_e2e.py`, `test_cycle_state.py` (in 8.1). (dep 5.2)
 - [ ] 5.3 `autopilot-roadmap/scripts/orchestrator.py`: mint token, store digest,
   take and persist the verified `roadmap_approval_ref` from `ExecutionAdapter.prepare`,
   emit v2 request; replace `_validate_dispatch_result` with `dispatch_contract`;
@@ -78,9 +101,11 @@
 - [ ] 6.1 Test first: `skills/tests/autopilot/test_emit_result.py`,
   `test_loop_state_v6.py`, `test_gate_check_reeval.py`. — SW all four requirements
 - [ ] 6.2 `autopilot.py`: LoopState v6 (`park`, `degradations`), v5 migration,
-  `_apply_transition` refuses while parked; gate session passes the marker's
-  `roadmap_approval_ref` into gate context. (dep 6.1) — SW Loop State Parks and
-  Degradations; TP
+  `_apply_transition` refuses while parked; the gate session constructs
+  `ApprovalGate` with its default `marker_reader`
+  (`dispatch_contract.read_launch_marker`) and passes no `roadmap_approval_ref` or
+  other scope value through the gate context, which D8 ignores. (dep 6.1) — SW Loop
+  State Parks and Degradations; TP
 - [ ] 6.3 `runner.py`: `emit-result`, `park`, `record-degradation`. (dep 6.2) — SW
   Code-Emitted Dispatch Result, Loop State Parks and Degradations
 - [ ] 6.4 `runner.py` + gate session: dispatched-vs-standalone authority (marker
@@ -90,9 +115,15 @@
   (dep 6.3)
   — SW Gate Authority and Re-Evaluation on Resume
 - [ ] 6.5 `skills/autopilot/SKILL.md`: worker protocol — `emit-result` + commit, `park`
-  on permission denial, `probe_command` only, no env probing; resync mirrors with
+  on permission denial, `probe_command` only, no env probing. Replace the
+  below-quorum `CLI_REVIEW_ENABLED=false` step: in a dispatched child (marker present)
+  keep review enabled and, at `PLAN_REVIEW` / `IMPL_REVIEW` entry, compare
+  `execution_profile.lanes.review` with `review_requirements.min_quorum[phase]` and run
+  `runner.py park --kind capability_unavailable --phase P --missing-lane ...` when
+  short; in a standalone run keep disabling review and run `runner.py
+  record-degradation --code review_skipped --phase PLAN_REVIEW`. Resync mirrors with
   `install.sh`. (dep 6.4) — SV Execution Profile and Review Requirements; SW
-  Code-Emitted Dispatch Result
+  Code-Emitted Dispatch Result, Honest Review Quorum
 
 ## 7. Review honesty  `[wp-review-honesty]` (deps: 6.3)
 
@@ -100,27 +131,34 @@
   and `skills/tests/autopilot/test_quorum_park.py`. — PI; SW Honest Review Quorum
 - [ ] 7.2 `review_dispatcher.py`: dry-invocation verification, `--json` output,
   env-free probe. (dep 7.1) — PI Dispatchable Vendor Verification
-- [ ] 7.3 `convergence_loop.py`: park `capability_unavailable` when a marker's
-  `review_requirements` is unmet; standalone degradation. (dep 7.1, 6.3) — SW Honest
-  Review Quorum
+- [ ] 7.3 `convergence_loop.py`: pre-dispatch guard that returns
+  `ConvergenceResult(reason="capability_unavailable")` with the missing lanes when it
+  is handed fewer verified lanes than `min_quorum`, before any dispatch; it writes no
+  loop state (the caller runs `runner.py park`, the only writer of `park`). (dep 7.1,
+  6.3) — SW Honest Review Quorum
 
 ## 8. Supervisor  `[wp-supervisor]` (deps: 1.1, 3.3, 5.3)
 
 - [ ] 8.1 Test first: extend `skills/tests/supervise/test_execution.py` and
   `test_gate_router.py` for token verify/rotate/reissue, cross-host reconcile,
-  provenance re-evaluation, dedupe escalation, degradations persistence. Update
-  `test_gate_router_e2e.py`; leave the existing `fixtures/execution/contracts/` v1
+  provenance re-evaluation, dedupe escalation (one `escalate_resume` record per
+  listed dispatch, design D9), degradations persistence. Update
+  `test_gate_router_e2e.py` and `test_cycle_state.py` (schema copies, 5.2a); leave the existing `fixtures/execution/contracts/` v1
   fixtures byte-unchanged (outcome 1: they must pass through the v1 reader) and add
   v2 fixtures beside them. — RO, SV
 - [ ] 8.2 `execution.py`: delete hand validators; `child_start` digest verify;
-  `reissue`; token rotation in `resume`; marker v2 contents including the supervisor's
+  `reissue`; token rotation in `resume`; `resume` accepts parked kinds
+  `permission_blocked` / `capability_unavailable` (expected gate `escalate_resume`,
+  `dedupe_fingerprint` recomputed and compared); marker v2 contents including the supervisor's
   `posture_digest` (D10a);
   `execution_profile` / `review_requirements` resolution in `prepare`; host-portable
   verify, rebind and reinitialize in `reconcile`. (dep 8.1) — RO Launch Token Digest,
   Host-Portable Attempt Isolation; SV Execution Profile and Review Requirements
 - [ ] 8.3 `gate_router.py`: `ANSWER_PATHS` table; provenance-aware
   `_apply_prior_record` (digest, human-final); `resolve_parked` for the two new kinds
-  with fingerprint dedupe and fan-out resume; typed `gate_answer` in continuation.
+  with fingerprint dedupe and fan-out resume (one per-dispatch `escalate_resume`
+  record carrying its own `lease_generation` and the shared `dedupe_fingerprint`, so
+  `require_approval_ref` keeps its per-dispatch checks); typed `gate_answer` in continuation.
   (dep 8.2) — SV Dispatch Result Closure, Typed Gate Answers With Provenance, Single
   Escalation Per Capability Park
 - [ ] 8.4 `skills/supervise/SKILL.md`: collect results by committed file path, profile
@@ -152,9 +190,9 @@
 
 | Requirement | Tasks |
 |---|---|
-| RO Published Dispatch Contract Schemas | 2.1, 2.2, 2.4, 4.1, 4.2, 5.3, 8.2, 9.6 |
+| RO Published Dispatch Contract Schemas | 2.1, 2.2, 2.3a, 2.4, 4.1, 4.2, 5.2, 5.2a, 5.3, 8.2, 9.6 |
 | RO Launch Token Digest | 2.3, 5.1, 5.2, 5.3, 8.2, 9.4 |
-| RO Host-Portable Attempt Isolation | 2.3, 5.1, 5.2, 8.2, 9.3 |
+| RO Host-Portable Attempt Isolation | 2.3, 4.3, 5.1, 5.2, 8.2, 9.3 |
 | RO Outcome-Only Resume Contract (MOD) | 5.3, 8.3, 9.2 |
 | RO Durable Delegated Attempt Ledger (MOD) | 5.3, 8.2, 9.2 |
 | SV Dispatch Result Closure | 1.1, 8.3, 9.1 |
@@ -164,6 +202,6 @@
 | SW Code-Emitted Dispatch Result | 4.2, 6.3, 6.5, 9.2 |
 | SW Loop State Parks and Degradations | 6.2, 6.3 |
 | SW Gate Authority and Re-Evaluation on Resume | 6.4, 9.2 |
-| SW Honest Review Quorum | 7.3 |
+| SW Honest Review Quorum | 6.5, 7.3 |
 | TP Roadmap-Approval-Scoped Auto Dispositions | 3.1, 3.2, 3.3, 6.2, 9.5 |
 | PI Dispatchable Vendor Verification | 7.1, 7.2 |
diff --git a/openspec/changes/dispatch-contract/work-packages.yaml b/openspec/changes/dispatch-contract/work-packages.yaml
index 89129b5..c449ac9 100644
--- a/openspec/changes/dispatch-contract/work-packages.yaml
+++ b/openspec/changes/dispatch-contract/work-packages.yaml
@@ -12,6 +12,10 @@ contracts:
     files:
     - openspec/schemas/dispatch-request.schema.json
     - openspec/schemas/dispatch-result.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/bounded-dispatch-context.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-result.schema.json
 defaults:
   priority: 5
   lock_ttl_minutes: 120
@@ -89,6 +93,10 @@ packages:
     - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
     - skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json
     - skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/**
+    - skills/tests/supervise/test_execution_contract.py
+    - skills/tests/install_sh/test_openspec_assets.py
     keys:
     - contract:dispatch-request
     - contract:dispatch-result
@@ -104,6 +112,10 @@ packages:
     - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
     - skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json
     - skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/**
+    - skills/tests/supervise/test_execution_contract.py
+    - skills/tests/install_sh/test_openspec_assets.py
     read_allow:
     - '**'
   worktree:
@@ -210,7 +222,9 @@ packages:
   locks:
     files:
     - skills/shared/dispatch_contract.py
+    - skills/shared/environment_profile.py
     - skills/tests/shared/test_dispatch_contract.py
+    - skills/tests/shared/test_environment_profile_host_id.py
     keys:
     - feature:dispatch-contract:contractlib
     ttl_minutes: 120
@@ -218,7 +232,9 @@ packages:
   scope:
     write_allow:
     - skills/shared/dispatch_contract.py
+    - skills/shared/environment_profile.py
     - skills/tests/shared/test_dispatch_contract.py
+    - skills/tests/shared/test_environment_profile_host_id.py
     - skills/tests/shared/fixtures/dispatch_contract/**
     read_allow:
     - '**'
@@ -233,7 +249,8 @@ packages:
     steps:
     - name: wp-contract-lib tests
       kind: command
-      command: skills/.venv/bin/python -m pytest skills/tests/shared/test_dispatch_contract.py -q
+      command: skills/.venv/bin/python -m pytest skills/tests/shared/test_dispatch_contract.py skills/tests/shared/test_environment_profile_host_id.py
+        -q
       cwd: .
       expect_exit_code: 0
       evidence:
@@ -267,6 +284,8 @@ packages:
     - skills/tests/roadmap-runtime/test_checkpoint_legacy_migration.py
     - skills/tests/roadmap-runtime/test_dispatch_scheduler.py
     - skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py
+    - skills/tests/roadmap-runtime/test_readiness.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch.py
     keys:
     - feature:dispatch-contract:ledger
     ttl_minutes: 120
@@ -280,6 +299,8 @@ packages:
     - skills/tests/roadmap-runtime/test_checkpoint_legacy_migration.py
     - skills/tests/roadmap-runtime/test_dispatch_scheduler.py
     - skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py
+    - skills/tests/roadmap-runtime/test_readiness.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch.py
     read_allow:
     - '**'
   worktree:
@@ -452,6 +473,7 @@ packages:
     - skills/tests/supervise/test_execution.py
     - skills/tests/supervise/test_gate_router.py
     - skills/tests/supervise/test_gate_router_e2e.py
+    - skills/tests/supervise/test_cycle_state.py
     - skills/tests/supervise/fixtures/execution/**
     read_allow:
     - '**'

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/dispatch-contract/design.md
- openspec/changes/dispatch-contract/proposal.md
- openspec/changes/dispatch-contract/tasks.md
- openspec/changes/dispatch-contract/work-packages.yaml

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

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

The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2. The existing `openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json` SHALL be kept unchanged as the version-1 reader schemas that a version-1 document is validated against before upgrade, `delegated-dispatch-attempt.schema.json` SHALL be the only definition of a checkpoint attempt (`checkpoint.schema.json` SHALL `$ref` it), and `bounded-dispatch-context.schema.json` SHALL be `$ref`'d by the version-2 request. Schema validation of a version-1 document SHALL be host-independent; only the upgrade step, which takes `repo_root`, `managed_root`, and `host_id` explicitly, depends on the host.

#### Scenario: Existing fixtures validate against the published schemas
- **WHEN** the test suite validates the byte-unchanged fixtures under `skills/tests/supervise/fixtures/execution/contracts/` with this mapping: `valid-request.json` and `invalid-continuation-without-kind.json` through `dispatch_contract.validate_request`; each entry (`success`, `parked`) of `valid-results.json` through `dispatch_contract.validate_result`; `valid-prepared-attempt.json` through the checkpoint attempt validator after the legacy reader converts its `launch_token`
- **THEN** every `valid-*` document SHALL validate and every `invalid-*` document SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer, on any host and without a managed worktree root existing at the fixtures' `/workspace/...` paths

#### Scenario: No hand-written result field set remains
- **WHEN** a guard test scans `skills/supervise/scripts/execution.py` and `skills/autopilot-roadmap/scripts/orchestrator.py`
- **THEN** neither file SHALL define `_RESULT_REQUIRED`, `_RESULT_ALLOWED`, `_validate_result`, or `_validate_dispatch_result`
- **AND** `checkpoint.schema.json`'s attempt `result` property SHALL be a `$ref` to `dispatch-result.schema.json`

#### Scenario: Schema mirrors stay identical
- **WHEN** the parity test compares `openspec/schemas/dispatch-*.schema.json` and `checkpoint.schema.json` with their `install_assets` copies
- **THEN** the bytes SHALL be identical, and a difference SHALL fail the test naming the file

#### Scenario: A version-1 result is upgraded, not rejected
- **WHEN** `ExecutionAdapter.apply` receives a schema-valid version-1 `success` result whose absolute `worktree_path` lies inside the current host's managed worktree root
- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a relative `worktree_ref`, an `evidence.loop_state_path` relative to that worktree, and the current `host_id`, and applied

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
- **THEN** apply SHALL rej

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


### Open ledger items
- [1] D2 claims the boundary is defined only by hand validators plus an inline checkpoint copy, but published JSON Schemas already exist at openspec/contracts/roadmap-orchestration/schemas/{supervised-dispatch-request,supervised-dispatch-result,delegated-dispatch-attempt,bounded-dispatch-context}.schema.json (with $id https://agentic-coding-tools.dev/contracts/...), consumed by skills/tests/supervise/test_execution_contract.py, test_execution.py:386, roadmap-runtime/test_dispatch_scheduler.py:34 and autopilot-roadmap/test_supervised_dispatch_e2e.py:42. Adding openspec/schemas/dispatch-*.schema.json without deciding what happens to them creates a fourth definition, the exact root cause the change exists to remove.
- [2] Why states the dispatch request and result 'exist only as three hand-kept validators ... plus test fixtures', and Impact lists only openspec/schemas/ files. openspec/contracts/roadmap-orchestration/schemas/ already publishes request, result, attempt and context schemas (listed in docs/architecture-analysis/contracts-inventory.md). The problem statement and Impact table are factually incomplete.
- [3] Scenario 'Existing fixtures validate against the published schemas' requires every valid-* fixture under skills/tests/supervise/fixtures/execution/contracts/ to pass validate_request/validate_result, but valid-prepared-attempt.json is a checkpoint attempt (with raw launch_token), and valid-results.json is a map {success, parked} rather than a result. Its v1 success result also carries absolute worktree_path and evidence.loop_state_path under /workspace/.git-worktrees, which the 'cannot be made portable' scenario would reject on any test host. The scenario is unexecutable as worded, and the requirement does not relate the existing openspec/contracts/roadmap-orchestration/schemas/ files to the new single definition.
- [4] Making checkpoint.schema.json's attempt result a $ref breaks every existing validator of that schema: roadmap-runtime/scripts/models.py validate_against_schema (lines 956-973) builds a bare Draft202012Validator with no registry, used by resolve_readiness.py:113 and models.py:1135; and tests that copy only checkpoint.schema.json into a tmp repo (supervise/test_execution.py _workspace, test_gate_router.py:54, test_gate_router_e2e.py:57, test_cycle_state.py:115, roadmap-runtime/test_readiness.py:105, autopilot-roadmap/test_supervised_dispatch.py:25, test_supervised_dispatch_e2e.py:95) would then fail with an unresolvable reference. No task updates the loader or those copies. Tasks also omit the existing contract schemas (finding 1), a host_id function in skills/shared/environment_profile.py (D7 cites it; the module has only detect() and its layers), and the install manifest test skills/tests/install_sh/test_openspec_assets.py.
- [5] Write scopes omit files the plan must edit: openspec/contracts/roadmap-orchestration/schemas/*.schema.json and skills/tests/supervise/test_execution_contract.py (no package); skills/shared/environment_profile.py (host_id, D7; no package); skills/tests/roadmap-runtime/test_readiness.py, skills/tests/supervise/test_cycle_state.py, skills/tests/autopilot-roadmap/test_supervised_dispatch.py and skills/tests/install_sh/test_openspec_assets.py (schema copy sites broken by the checkpoint $ref; no package). Scope enforcement will reject these edits.
- [6] D9 says one operator answer resumes every attempt sharing a fingerprint, but the resume path verifies a record bound to one dispatch: gate_router.require_approval_ref (gate_router.py:1095-1140) rejects a record whose dispatch_id differs and, for escalate_resume, whose lease_generation differs; ExecutionAdapter.resume rejects any kind other than pending_gate/policy_pause (execution.py:852). D9 never defines the decision-record shape for a fingerprint subject, so the fan-out cannot pass the existing verification.
- [7] Modified scenario 'Resume an authorized parked attempt' requires 'a subject matching the dispatch', replacing the base 'matching dispatch_id' with an undefined term. With D9 fingerprint subjects the verifiable condition is unclear and an implementer could accept a record whose subject lists the dispatch but whose lease_generation is stale.
- [8] Honest Review Quorum cannot be met by the tasked edits. Below quorum, skills/autopilot/SKILL.md (lines 175-179) sets CLI_REVIEW_ENABLED=false before run_loop, so PLAN_REVIEW is skipped and convergence_loop never runs; task 7.3 puts the park in convergence_loop.py, which therefore never fires for a dispatched child, and it also contradicts the skill-workflow rule that runner.py park is the only writer of park. The standalone review_skipped degradation likewise cannot come from convergence_loop because no review runs.
- [9] D10 defines counting_lanes as 'verified lanes ordered by the cost_policy.tiers ladder'. The skill-workflow scenario requires missing_lanes to name 'the counting lanes not verified', which is always empty under that definition, so every capability_unavailable park fingerprints to sha256(phase, []) and D9's 'different missing lanes are separate escalations' cannot hold.
- [10] Task 6.2 says the gate session 'passes the marker's roadmap_approval_ref into gate context', but D8 and the trust-posture requirement say a context-supplied roadmap_approval_ref is ignored and the gate reads the marker only through its marker_reader seam. Implemented as tasked, either scope never applies or the context path becomes the trust channel D8 forbids.
- [11] D1's v1 upgrade converts only worktree_path, but v1 results also carry an absolute evidence.loop_state_path (see fixtures/execution/contracts/valid-results.json), while Host-Portable Attempt Isolation forbids persisting absolute paths in the result. An upgraded v1 result would still carry an absolute path into checkpoint outcome metadata.
- [12] D9 says the stored command is 'the output of sanitize_session_log.sanitize()', but sanitize() returns a (content, redactions) tuple (sanitize_session_log.py:177).
- [13] D7 reinitializes a parked attempt on another host by incrementing its generation, which invalidates any already-recorded escalate_resume approval bound to the old lease_generation; the operator would need to answer again.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

Hunt only in the attached last-fix diff. Re-verify open ledger items. Do not re-open retired or parked items.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 2. Focus on remaining issues.