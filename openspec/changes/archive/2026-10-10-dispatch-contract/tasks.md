# Tasks: Publish the supervisor-worker dispatch contract

> Change ID: `dispatch-contract`
> Packages and write scopes: `work-packages.yaml`. Each task names its package
> (`[wp-*]`), its dependencies, and the requirement(s) it implements
> (RO = roadmap-orchestration, SV = supervise, SW = skill-workflow,
> TP = trust-posture, PI = parallel-infrastructure).

## 1. Merge the narrow fix  `[wp-merge-narrow-fix]` (no deps)

- [x] 1.1 Merge `origin/openspec/supervise-pending-escalate-answer` (6e6e9a6) into
  `openspec/dispatch-contract`; resolve nothing by re-implementing. Run
  `skills/tests/supervise/test_gate_router.py`. — SV Dispatch Result Closure
  (pending_gate/escalate_resume path)

## 2. Schemas  `[wp-dispatch-schemas]` (no deps)

- [x] 2.1 Write `openspec/schemas/dispatch-result.schema.json` v2: outcome classes,
  `parked` `oneOf` per kind (D3), `gate` as the `Gate` enum, `degradations` code enum
  (D10), isolation echo `{worktree_ref, branch, host_id}`, evidence. — RO Published
  Dispatch Contract Schemas
- [x] 2.2 Write `openspec/schemas/dispatch-request.schema.json` v2: identity, raw
  `launch_token`, host-portable `isolation`, `execution_profile`,
  `review_requirements`, optional `continuation` and `gate_answer`,
  `roadmap_approval_ref`. — RO Published Dispatch Contract Schemas; SV Execution
  Profile and Review Requirements
- [x] 2.3 Edit `checkpoint.schema.json`: attempt `result` -> `$ref`; `launch_token` ->
  `launch_digest` (`^sha256:[0-9a-f]{64}$`); attempt `roadmap_approval_ref`; isolation
  `{mode, worktree_ref, branch, host_id}`; parked kinds extended; `rebound` history state. — RO Launch Token Digest,
  Host-Portable Attempt Isolation
- [x] 2.3a Existing contract schemas (design D2): edit
  `openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json`
  to the new attempt shape and make `checkpoint.schema.json` `dispatch_attempts.items`
  `$ref` it; keep `supervised-dispatch-request`/`-result.schema.json` byte-unchanged as
  v1 reader schemas; `$ref` `bounded-dispatch-context.schema.json` from the v2
  request. Repoint `skills/tests/supervise/test_execution_contract.py` at the v2/v1
  schemas through a registry. (dep 2.1-2.3) — RO Published Dispatch Contract Schemas
- [x] 2.4 Mirror 2.1-2.3a into `skills/roadmap-runtime/install_assets/openspec/`
  (`schemas/` and `contracts/roadmap-orchestration/schemas/`) and add the byte-parity
  test; add the new installed paths to
  `skills/tests/install_sh/test_openspec_assets.py`. (dep 2.1-2.3a) — RO Published
  Dispatch Contract Schemas

## 3. Posture provenance and scope  `[wp-posture]` (no deps)

- [x] 3.1 Test first: `skills/tests/shared/test_trust_posture_scope.py` covering every
  TP scenario (digest stability, `unscoped` validation). — TP
- [x] 3.2 `trust_posture.py`: `posture_digest()`, `unscoped` sub-config parse and
  validation; `trust-posture.schema.json` and `TRUST_POSTURE.template.md` document it.
  (dep 3.1) — TP Roadmap-Approval-Scoped Auto Dispositions
- [x] 3.3 `approval_gate.py`: `provenance` on every decision record; scoped `auto` for
  `proposal_approval` / `replan_required` using a `marker_reader` seam (context-supplied
  refs ignored); `scope` recorded. `gate-decision.schema.json` and
  `gate-request.schema.json` gain `provenance`, `scope`, `posture.posture_digest`.
  (dep 3.2) — TP; SV Typed Gate Answers With Provenance

## 4. Contract library  `[wp-contract-lib]` (deps: 2.4)

- [x] 4.1 Test first: `skills/tests/shared/test_dispatch_contract.py` — fixture
  validation, v1 upgrade (both scenarios), mapping table rows from D4, slug rule,
  marker reader. — RO Published Dispatch Contract Schemas; SW Code-Emitted Dispatch
  Result
- [x] 4.2 `skills/shared/dispatch_contract.py`: schema locator with install_assets
  fallback, `validate_request`, `validate_result`, `upgrade_v1`,
  `result_from_loop_state`, `dispatch_slug`, `read_launch_marker`,
  `DispatchContractError`; a `referencing.Registry` built from every schema under
  `openspec/schemas/` and `openspec/contracts/roadmap-orchestration/schemas/`
  (`$id`-keyed) and exported as `schema_registry(repo_root)`. (dep 4.1)
- [x] 4.3 `skills/shared/environment_profile.py`: add `host_id()` (cloud session
  environment ID when present, else a hash of the machine ID; never a hostname or
  username) with a unit test. — RO Host-Portable Attempt Isolation (D7)

## 5. Runtime ledger  `[wp-runtime-ledger]` (deps: 4.2)

- [x] 5.1 Test first: legacy-load tests that copy the archived checkpoint and the live
  `multiplayer-collaboration` checkpoint into `tmp_path` at test time (never commit a
  copy: both contain raw tokens); persisted-shape tests (no raw token, no absolute
  path). Update `test_delegated_checkpoint.py` and `test_dispatch_scheduler.py`,
  which pin `launch_token` today. — RO Launch Token Digest, Host-Portable Attempt Isolation
- [x] 5.2 `roadmap-runtime/scripts/models.py` + `checkpoint.py`: attempt fields
  `launch_digest` and portable isolation; legacy migration on load; `needs_rebind`;
  `validate_against_schema` builds its `Draft202012Validator` with
  `dispatch_contract.schema_registry(repo_root)` so the checkpoint's `$ref`s resolve
  (today it uses a bare validator, so `resolve_readiness.py` and checkpoint load would
  fail on an unresolvable reference). (dep 5.1)
- [x] 5.2a Update every test helper that copies only `checkpoint.schema.json` into a
  temporary repo to also copy the schemas it `$ref`s: `roadmap-runtime/test_readiness.py`,
  `autopilot-roadmap/test_supervised_dispatch.py`, `test_supervised_dispatch_e2e.py`
  (this package), and `supervise/test_execution.py`, `test_gate_router.py`,
  `test_gate_router_e2e.py`, `test_cycle_state.py` (in 8.1). (dep 5.2)
- [x] 5.3 `autopilot-roadmap/scripts/orchestrator.py`: mint token, store digest,
  take and persist the verified `roadmap_approval_ref` from `ExecutionAdapter.prepare`,
  emit v2 request; replace `_validate_dispatch_result` with `dispatch_contract`;
  `resolve_worktree()` for every path read; persist `degradations` in outcome
  metadata; refuse unroutable parked results at apply (calls the answer-path predicate
  injected by the adapter). (dep 5.2) — RO Outcome-Only Resume Contract, Durable
  Delegated Attempt Ledger

## 6. Autopilot child  `[wp-autopilot-child]` (deps: 3.3, 4.2)

- [x] 6.1 Test first: `skills/tests/autopilot/test_emit_result.py`,
  `test_loop_state_v6.py`, `test_gate_check_reeval.py`. — SW all four requirements
- [x] 6.2 `autopilot.py`: LoopState v6 (`park`, `degradations`), v5 migration,
  `_apply_transition` refuses while parked; the gate session constructs
  `ApprovalGate` with its default `marker_reader`
  (`dispatch_contract.read_launch_marker`) and passes no `roadmap_approval_ref` or
  other scope value through the gate context, which D8 ignores. (dep 6.1) — SW Loop
  State Parks and Degradations; TP
- [x] 6.3 `runner.py`: `emit-result`, `park`, `record-degradation`. (dep 6.2) — SW
  Code-Emitted Dispatch Result, Loop State Parks and Degradations
- [x] 6.4 `runner.py` + gate session: dispatched-vs-standalone authority (marker
  present => apply only `gate_answer`; worktree/marker posture-digest drift => no
  `auto`, park `pending_gate`); standalone `gate-check` re-evaluation on digest change;
  `gate-answer --approval-ref` with marker check; clears `park` for `escalate_resume`.
  (dep 6.3)
  — SW Gate Authority and Re-Evaluation on Resume
- [x] 6.5 `skills/autopilot/SKILL.md`: worker protocol — `emit-result` + commit, `park`
  on permission denial, `probe_command` only, no env probing. Replace the
  below-quorum `CLI_REVIEW_ENABLED=false` step: in a dispatched child (marker present)
  keep review enabled and, at `PLAN_REVIEW` / `IMPL_REVIEW` entry, compare
  `execution_profile.lanes.review` with `review_requirements.min_quorum[phase]` and run
  `runner.py park --kind capability_unavailable --phase P --missing-lane ...` when
  short; in a standalone run keep disabling review and run `runner.py
  record-degradation --code review_skipped --phase PLAN_REVIEW`. Resync mirrors with
  `install.sh`. (dep 6.4) — SV Execution Profile and Review Requirements; SW
  Code-Emitted Dispatch Result, Honest Review Quorum
- [x] 6.6 Supervisor follow-up (a): `autopilot._apply_transition` applies GATEKEEPER
  `proceed_with_review` (sets `val_review_enabled`, records `gate_verdict`) so the
  host-driven `runner.py transition` path schedules VAL_REVIEW like `run_loop`; tests in
  `test_loop_state_v6.py`. — SV Execution Profile and Review Requirements
- [x] 6.7 Supervisor follow-up (b): `emit-result` derives `parked` only from `park`,
  `pending_gate` or `ESCALATE`, so a parked result without that loop-state evidence is
  unproducible; `apply` accepts `park` evidence for the two new kinds. Covered in the
  `test_emit_result.py` matrix. — SW Code-Emitted Dispatch Result

## 7. Review honesty  `[wp-review-honesty]` (deps: 6.3)

- [x] 7.1 Test first: `skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py`
  and `skills/tests/autopilot/test_quorum_park.py`. — PI; SW Honest Review Quorum
- [x] 7.2 `review_dispatcher.py`: dry-invocation verification, `--json` output,
  env-free probe. (dep 7.1) — PI Dispatchable Vendor Verification
- [x] 7.3 `convergence_loop.py`: pre-dispatch guard that returns
  `ConvergenceResult(reason="capability_unavailable")` with the missing lanes when it
  is handed fewer verified lanes than `min_quorum`, before any dispatch; it writes no
  loop state (the caller runs `runner.py park`, the only writer of `park`). (dep 7.1,
  6.3) — SW Honest Review Quorum
- [x] 7.4 Supervisor follow-up 1: per-environment review quorum as data —
  `skills/parallel-infrastructure/review_quorum_policy.json` (cloud container below 2
  verified lanes -> `min_quorum` 1, with the sunset from the operator's TRUST_POSTURE.md
  decision of 2026-10-09; any other host keeps 2), resolved by
  `review_dispatcher.resolve_quorum_policy()` into `--check-vendors --json`
  `quorum_policy`, carried as `review_requirements.quorum_policy`
  (`dispatch-request.schema.json`). A single-lane review is detected by failed dispatch
  only and records `single_vendor_review` (phase, vendor). — SV Execution Profile and
  Review Requirements; SW Honest Review Quorum

- [x] 7.5 Supervisor follow-up (d): `review_packet._git_diff` resolves its base ref
  robustly (`main`, else `origin/main`), so a checkout with only the remote-tracking
  base no longer produces an empty review packet; test in `test_review_packet.py`
  (one-file scope extension to `review_packet.py`). — SW Honest Review Quorum
- [x] 7.6 Supervisor follow-up (d), IMPL_ITERATE: `converge(..., base_ref=None)`
  passes `base_ref` through to `build_review_packet`, so a stacked branch diffs
  against its PR base; `None` keeps `DEFAULT_BASE_REF`. Tests in
  `skills/tests/autopilot/test_convergence_loop.py`. — SW Honest Review Quorum
- [x] 7.7 Supervisor follow-up (d), IMPL_ITERATE: the post-fix scope check in
  `converge()` excludes converge's own `artifacts_dir` bookkeeping
  (`.review-ledger/`, `.review-cache/`), so a fix that edits only an allowed path is
  not rejected by `reject_out_of_scope_fix`. Regression test in
  `skills/tests/autopilot/test_convergence_loop.py`. — SW Honest Review Quorum

## 8. Supervisor  `[wp-supervisor]` (deps: 1.1, 3.3, 5.3)

- [x] 8.1 Test first: extend `skills/tests/supervise/test_execution.py` and
  `test_gate_router.py` for token verify/rotate/reissue, cross-host reconcile,
  provenance re-evaluation, dedupe escalation (one `escalate_resume` record per
  listed dispatch, design D9), degradations persistence. Update
  `test_gate_router_e2e.py` and `test_cycle_state.py` (schema copies, 5.2a); leave the existing `fixtures/execution/contracts/` v1
  fixtures byte-unchanged (outcome 1: they must pass through the v1 reader) and add
  v2 fixtures beside them. — RO, SV
- [x] 8.2 `execution.py`: delete hand validators; `child_start` digest verify;
  `reissue`; token rotation in `resume`; `resume` accepts parked kinds
  `permission_blocked` / `capability_unavailable` (expected gate `escalate_resume`,
  `dedupe_fingerprint` recomputed and compared); marker v2 contents including the supervisor's
  `posture_digest` (D10a);
  `execution_profile` / `review_requirements` resolution in `prepare`; host-portable
  verify, rebind and reinitialize in `reconcile`. (dep 8.1) — RO Launch Token Digest,
  Host-Portable Attempt Isolation; SV Execution Profile and Review Requirements
- [x] 8.3 `gate_router.py`: `ANSWER_PATHS` table; provenance-aware
  `_apply_prior_record` (digest, human-final); `resolve_parked` for the two new kinds
  with fingerprint dedupe and fan-out resume (one per-dispatch `escalate_resume`
  record carrying its own `lease_generation` and the shared `dedupe_fingerprint`, so
  `require_approval_ref` keeps its per-dispatch checks); typed `gate_answer` in continuation.
  (dep 8.2) — SV Dispatch Result Closure, Typed Gate Answers With Provenance, Single
  Escalation Per Capability Park
- [x] 8.4 `skills/supervise/SKILL.md`: collect results by committed file path, profile
  resolution, new park kinds; resync mirrors. (dep 8.3)

## 9. Integration  `[wp-integration]` (deps: 6.5, 7.3, 8.4)

- [x] 9.1 Closure contract test `skills/tests/supervise/test_dispatch_closure.py`,
  schema-derived enumeration plus the mutated-schema negative case. — SV Dispatch
  Result Closure (outcome 3)
- [x] 9.2 End-to-end test `skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py`:
  prepare -> child_start -> loop-state shapes -> `emit-result` -> `apply` for every
  shape; includes posture flip vs human rejection and the two single-escalation
  cases. — outcomes 2, 4, 5
- [x] 9.3 Cross-host test: commit a checkpoint on host id A, reconcile with host id B
  (rebind, reinitialize, quarantine, evidence mismatch). — outcome 7
- [x] 9.4 Landable fixture `skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`
  generated by the e2e harness with live attempts, plus the keyword unit test; confirm
  no `.gitleaks.toml` change. Run `gitleaks detect --no-git --source
  skills/tests/roadmap-runtime/fixtures` locally when the binary is present. —
  outcome 6
- [x] 9.5 Scoped-auto e2e: dispatched child with marker ref proceeds; standalone run
  blocks with `scope: unscoped`. — outcome 8
- [x] 9.6 Full suites: `skills/.venv/bin/python -m pytest skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure}`,
  `openspec validate dispatch-contract --strict`, existing fixtures unchanged. —
  outcome 1

- [x] 9.7 Supervisor follow-ups (c), (e) and plan sync: design.md records the
  per-environment quorum policy as data (D10), the `main`-rooted worktree launchpad as
  a known constraint with an open follow-up, and the implementation notes; the
  supervise and skill-workflow spec deltas gain the quorum-policy, single-lane and
  GATEKEEPER scenarios; proposal.md gains "Landing approach for PR #662" (squash merge
  so the SHA-allowlisted token commits never enter `main`; no history rewritten).

## Traceability

| Requirement | Tasks |
|---|---|
| RO Published Dispatch Contract Schemas | 2.1, 2.2, 2.3a, 2.4, 4.1, 4.2, 5.2, 5.2a, 5.3, 8.2, 9.6 |
| RO Launch Token Digest | 2.3, 5.1, 5.2, 5.3, 8.2, 9.4 |
| RO Host-Portable Attempt Isolation | 2.3, 4.3, 5.1, 5.2, 8.2, 9.3 |
| RO Outcome-Only Resume Contract (MOD) | 5.3, 8.3, 9.2 |
| RO Durable Delegated Attempt Ledger (MOD) | 5.3, 8.2, 9.2 |
| SV Dispatch Result Closure | 1.1, 8.3, 9.1 |
| SV Typed Gate Answers With Provenance | 3.3, 8.3, 9.2 |
| SV Execution Profile and Review Requirements | 2.2, 6.5, 8.2, 9.2 |
| SV Single Escalation Per Capability Park | 8.3, 9.2 |
| SW Code-Emitted Dispatch Result | 4.2, 6.3, 6.5, 9.2 |
| SW Loop State Parks and Degradations | 6.2, 6.3 |
| SW Gate Authority and Re-Evaluation on Resume | 6.4, 9.2 |
| SW Honest Review Quorum | 6.5, 7.3 |
| TP Roadmap-Approval-Scoped Auto Dispositions | 3.1, 3.2, 3.3, 6.2, 9.5 |
| PI Dispatchable Vendor Verification | 7.1, 7.2 |
