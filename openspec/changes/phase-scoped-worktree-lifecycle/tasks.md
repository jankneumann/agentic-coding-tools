# Tasks: phase-scoped-worktree-lifecycle

All tasks use test-first ordering. Sizes describe one focused agent session; no task is XL and no task is L.

## 0. Executable prerequisite preflight

- [x] 0.1 (S) Write mocked repository/PR/Git tests that fail closed for absent, open, duplicate, wrong-repository, wrong-base, caller-supplied-SHA, non-ancestral, missing-surface, and 41-63-character invalid Git object-id prerequisite evidence
  **Contracts**: `contracts/prerequisites.yaml`, `contracts/schemas/baseline-gates.schema.json`
  **Dependencies**: None
  **Files**: `skills/tests/implement-feature/test_prerequisite_preflight.py`

- [x] 0.2 (S) Implement the prerequisite resolver that obtains authoritative merged PR metadata, fetches the configured remote/base, proves ancestry to fetched base plus feature HEAD, validates named surfaces, records the implementation diff base, and atomically writes schema-valid evidence
  **Dependencies**: 0.1
  **Files**: `skills/implement-feature/scripts/prerequisite_preflight.py`

- [x] 0.3 Write coordinated-execution regression coverage for the exact `contracts/prerequisites.yaml#execution_gate` declaration, proving the scheduler refuses completion until evidence is integrated and reverified on feature HEAD and every dependent worktree uses that recorded HEAD as its minimum base
  **Dependencies**: 0.2
  **Spec scenarios**: `skill-workflow` — Verified preflight commit is the dependent worktree base
  **Files**: `skills/tests/implement-feature/test_coordinated_preflight.py`, `skills/parallel-infrastructure/scripts/tests/test_dag_scheduler.py`

- [x] 0.4 Implement the generic feature-HEAD completion barrier, then commit it and explicitly reload or reinstate the scheduler and integration orchestrator from that feature commit before this run attempts live preflight or dependent dispatch
  **Dependencies**: 0.3
  **Files**: `skills/implement-feature/SKILL.md`, `skills/parallel-infrastructure/scripts/dag_scheduler.py`, `skills/parallel-infrastructure/scripts/integration_orchestrator.py`

- [ ] 0.5 Run the live resolver in the managed shared feature worktree, commit `baseline-gates.json`, and use the reloaded barrier to reverify the evidence and record the exact dependent base before satisfying the package dependency or creating dependent worktrees; if either prerequisite is not merged and reconciled or feature-HEAD CAS loses a race, leave dependents blocked
  **Dependencies**: 0.4
  **Files**: `openspec/changes/phase-scoped-worktree-lifecycle/baseline-gates.json`

## 1. Registry and activity-guard contract

- [x] 1.1 (M) Write registry identity and controller-fencing tests covering the exact triple across acquire/resume/renew/assert/release/teardown and JSON output, wrong-controller conflicts, generation-bound evidence keys, intentional cross-entry lease-id collisions, locking, retention, corruption, and isolation
  **Spec scenarios**: `worktree` — Owner acquires and renews the default lease; Wrong ownership component cannot renew or release a live lease; Duplicate live controller cannot reuse the same fence; Automatic commands and results carry the exact fence; Matching release is idempotent; Fresh automatic setup publishes through a durable reservation; Setup crash boundaries reconcile exact side effects; Provisioning reservation blocks sync points; Durability target binds remote identity and fetched ref; AC-08; Process evidence is collision-safe across entries; AC-09; AC-11; Concurrent lifecycle updates preserve both owners' records; Corrupt registry blocks safety decisions without rewrite; Lease mutations short-circuit under harness isolation
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/worktree-process-evidence.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D1-D6
  **Dependencies**: None
  **Files**: `skills/worktree/scripts/tests/test_worktree.py`, `skills/worktree/scripts/tests/test_environment_aware.py`, `skills/shared/tests/test_worktree_lifecycle.py`, `skills/tests/worktree/test_setup_prototype.py`, `skills/tests/worktree/fixtures/**`

- [x] 1.2 (M) Implement the portable locked schema-v2 interpreter, controller-bound core lease operations, collision-safe process evidence, retention, and source/install import boundary
  **Dependencies**: 1.1
  **Files**: `skills/shared/worktree_lifecycle.py`, `skills/worktree/scripts/worktree.py`, `skills/worktree/SKILL.md`

- [x] 1.3 (M) Write fixed reservation TTL/expiry, exact completed-setup replay, crash reconciliation, side-effect-preserving setup recovery, lease-free safe teardown, separately confirmed force-teardown, deterministic legacy generation/null-controller release, null-target bind, generic-GC exclusion, teardown-before-release, recovery audit, and generation-bound evidence tests covering every side-effect boundary and exact-triple conflict
  **Spec scenarios**: `worktree` — Pre-existing unleased state is not silently adopted; Expired takeover quarantines live or unknown process evidence; Clean durable expired takeover uses a new fence; PID reuse is stale rather than live evidence; Successful finalization tears down before lease release; Unsafe teardown quarantines and clears in one transaction; Teardown reconciles a crash after Git removal; Bulk owner release quarantines preserved checkouts; Explicit recovery adoption populates a complete manual lease; Force-adopt audit survives recovery clearing and teardown; Legacy setup remains compatible but is not ordinarily adoptable; Expired setup reservation is reconciled explicitly; Exact published setup replay survives response loss; Unleased quarantine is disposed safely; Automatic teardown has no force mode
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/worktree-process-evidence.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D2-D8
  **Dependencies**: 1.2
  **Files**: `skills/worktree/scripts/tests/test_worktree.py`, `skills/shared/tests/test_worktree_lifecycle.py`, `skills/tests/worktree/test_setup_prototype.py`, `skills/tests/worktree/fixtures/**`

- [x] 1.4 (M) Implement bounded staged setup reservations, exact completed-setup receipts, side-effect-preserving setup reconciliation, safe lease-free recovery teardown, separately named audited force-teardown, deterministic legacy generation and null-controller release, generation-fenced null-target bind, exact-old/new resume fencing, generic autopilot-envelope GC exclusion, compatibility setup path, and teardown-or-quarantine finalization
  **Dependencies**: 1.3
  **Files**: `skills/shared/worktree_lifecycle.py`, `skills/worktree/scripts/worktree.py`, `skills/worktree/SKILL.md`

- [x] 1.5 (S) Write active-agent guard tests for live, released, expired, retained, legacy, malformed, corrupt entries, plus all unfinished setup reservations as indeterminate non-activity blockers with expired reservations explicitly marked recovery-required
  **Spec scenarios**: `worktree` — AC-08, AC-09, AC-11, Corrupt registry blocks safety decisions without rewrite; `coordinator-kanban-viz` — AC-02; Unfinished reservation blocks sync points without appearing active
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`
  **Design decisions**: D1-D6
  **Dependencies**: 1.2
  **Files**: `skills/shared/tests/test_active_agents.py`

- [x] 1.6 (S) Make the local active-agent guard report current activity separately while conservatively blocking sync points on current activity or any unfinished reservation and labeling expired reservations for explicit reconciliation
  **Dependencies**: 1.4, 1.5
  **Files**: `skills/shared/active_agents.py`

- [x] Checkpoint: run worktree plus shared guard tests; inspect the cumulative diff; verify package scope plus migration safety.

## 2. Standalone phase lifecycle and session backstop

- [ ] 2.1 (M) Write process-level lifecycle-controller tests for controller-bound begin/retry/assert/renew/finalize, renewal loss, teardown without prior release, unsafe teardown without follow-up release, exact-triple command/output propagation, generation-bound teardown retry, and all-tier finalization
  **Spec scenarios**: `skill-workflow` — Durable push precedes phase teardown; Failed phase still finalizes activity; AC-01; Proposal artifacts fail strict validation; AC-06; Later phase recreates from durable remote state; `worktree` — Expired writer is fenced after same-owner resume; Successful finalization tears down before lease release; Unsafe teardown quarantines and clears in one transaction; Acquire cannot race owner-checked disposal
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`, `contracts/schemas/worktree-registry-v2.schema.json`
  **Design decisions**: D7-D8
  **Dependencies**: 1.4, 1.6
  **Files**: `skills/shared/tests/test_phase_lifecycle.py`, `skills/tests/plan-feature/test_skill_contract.py`, `skills/tests/implement-feature/test_skill_contract.py`, `skills/tests/iterate-on-plan/test_skill_contract.py`, `skills/tests/iterate-on-implementation/test_skill_contract.py`, `skills/tests/validate-feature/test_skill_contract.py`

- [ ] 2.2 (M) Implement the executable controller-bound renew/assert/finalize controller with checkpoint-before-teardown and atomic quarantine-plus-clear ordering, then add standalone/continuous lifecycle modes plus PR provenance trailers to planning, implementation, iteration, and validation skills
  **Dependencies**: 2.1
  **Files**: `skills/shared/phase_lifecycle.py`, `skills/plan-feature/SKILL.md`, `skills/implement-feature/SKILL.md`, `skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`, `skills/validate-feature/SKILL.md`

- [ ] 2.3 (M) Write package and nested-workflow tests for parent-ref durability targets, parent-only continuous renewal, inherited triple assertions, and post-integration teardown-before-release
  **Spec scenarios**: `skill-workflow` — Package worktrees use leases rather than pins; Worktrees are finalized after integration; AC-07
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`, `contracts/schemas/worktree-registry-v2.schema.json`
  **Design decisions**: D7-D9
  **Dependencies**: 2.2
  **Files**: `skills/shared/tests/test_phase_lifecycle.py`, `skills/tests/implement-feature/test_skill_contract.py`, `skills/tests/validate-feature/test_skill_contract.py`

- [ ] 2.4 (M) Implement package parent-ref durability and parent-controller-only renewal across phase/package dispatch and teardown-or-quarantine finalization
  **Dependencies**: 2.3
  **Files**: `skills/shared/phase_lifecycle.py`, `skills/implement-feature/SKILL.md`, `skills/validate-feature/SKILL.md`

- [ ] 2.5 (S) Write session-finalization tests for the inventory-declared `session_backstop`, exact owner/session release, preserved prior-controller evidence, different/null third-session identity, absent-entry idempotency, and proof that hooks call only `release-session` and never teardown/recovery or autopilot-envelope mutation
  **Spec scenarios**: `skill-workflow` — Session end releases only matching owners; `worktree` — Wrong ownership component cannot renew or release a live lease; Unsafe finalization quarantines recovery state
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D5, D10
  **Dependencies**: 1.4
  **Files**: `skills/tests/session-bootstrap/test_deregister_agent.py`, `agent-coordinator/tests/test_install_hooks.py`

- [ ] 2.6 (S) Add release-session-only best-effort local lease cleanup to shipped session hooks
  **Dependencies**: 2.5
  **Files**: `skills/session-bootstrap/scripts/hooks/deregister_agent.py`, `skills/session-bootstrap/SKILL.md`, `agent-coordinator/scripts/deregister_agent.py`, `agent-coordinator/scripts/install_hooks.py`

- [ ] 2.7 (M) Write mutating-skill inventory completeness and compatibility tests that scan every canonical setup, heartbeat, pin, active-agent, registry, coordinator projection, infrastructure-provider, documentation-consumer, and session-backstop path and require an exact inventory row or explicit exemption
  **Contracts**: `contracts/mutating-skill-inventory.yaml`, `contracts/cli/worktree-lifecycle.yaml`
  **Dependencies**: 2.2
  **Files**: `skills/tests/lifecycle-consumers/**`

- [ ] 2.8 (M) Migrate the lifecycle-consumer package's standalone, continuous-parent, and child launchers to the shared controller, including prototype retained-after-lease-release behavior; phase-owned launchers are migrated by 2.2 and autopilot/merge-owned launchers remain in their own packages
  **Dependencies**: 2.7
  **Files**: `skills/{archive-roadmap,autopilot-roadmap,changelog-version,explore-feature,fix-scrub,plan-roadmap,prototype-feature,quick-task,refresh-architecture}/**`

- [ ] 2.9 (M) Migrate hybrid sync-point, sync-point, and registry-reader consumers to canonical live-lease semantics and remove stale pinned-or-heartbeat prose/direct reads
  **Dependencies**: 2.7
  **Files**: `skills/{cleanup-feature,update-specs,project-context-refresh,expedite,review-artifacts}/**`, `skills/tests/lifecycle-consumers/**`

- [ ] Checkpoint: run lifecycle skill plus session-hook tests; verify every exit path tears down or quarantines only its exact ownership triple after durable output.

## 3. Pull-request delivery classification and merge routing

- [ ] 3.1 (M) Write exhaustive truth-table and schema-fixture tests for proposal, implementation-with-plan-refinement, mixed-without-base-plan, legacy, unknown paths, conflicting/duplicate/invalid/missing markers, truncated/failed diffs, failed base/head inspection, plus immutable base/head SHAs; negative fixtures MUST reject non-ambiguous stages for every incomplete acquisition state
  **Spec scenarios**: `merge-pull-requests` — AC-10 classification; Conflicting marker fails safe and warns; Legacy implementation PR remains processable
  **Contracts**: `contracts/schemas/pr-delivery-classification.schema.json`
  **Design decisions**: D11-D12
  **Dependencies**: None
  **Files**: `skills/tests/merge-pull-requests/test_delivery_classification.py`, `skills/tests/merge-pull-requests/test_classify.py`

- [ ] 3.2 (M) Implement the pure delivery classifier; enrich PR discovery without changing portable origin results
  **Dependencies**: 3.1
  **Files**: `skills/merge-pull-requests/scripts/pr_delivery.py`, `skills/merge-pull-requests/scripts/discover_prs.py`, `skills/shared/github_classifier.py`

- [ ] 3.3 (M) Write independent vendor-routing tests for verified Claude-authored proposal, implementation, mixed, unavailable-vendor, conflicting, plus unverified-claim cases
  **Spec scenarios**: `merge-pull-requests` — AC-04; AC-05; Unavailable independent vendor is explicit; Unverified vendor claim cannot exclude a reviewer
  **Contracts**: `contracts/schemas/pr-delivery-classification.schema.json`
  **Design decisions**: D12-D13
  **Dependencies**: 3.1
  **Files**: `skills/tests/merge-pull-requests/test_vendor_review.py`

- [ ] 3.4 (M) Implement author-vendor provenance plus stage-scoped Codex/Grok/Pi review prompts
  **Dependencies**: 3.2, 3.3
  **Files**: `skills/merge-pull-requests/scripts/vendor_review.py`

- [ ] Checkpoint: run delivery-classifier plus vendor-review tests; inspect prompts to confirm proposal reviews cannot request a code diff.

- [ ] 3.5 (M) Write ambiguity-disposition, append-only override-history, and canonical-digest tests covering pre-revision merge-plan nodes initialized with empty history under lock, record/honor/invalidate events, every binding change, newly clear and still-ambiguous results, clear-stage rejection, selected/effective equality, RFC-8785 normalization, Unicode, fixed expected hash, and cross-process parity
  **Spec scenarios**: `merge-pull-requests` — Operator disposition is explicit and auditable; Stale operator override remains auditable; Classification digest is deterministic semantic evidence
  **Contracts**: `contracts/schemas/merge-plan-delivery-fields.schema.json`, `contracts/schemas/pr-delivery-classification.schema.json`
  **Design decisions**: D14-D15
  **Dependencies**: 3.2
  **Files**: `skills/tests/merge-pull-requests/test_delivery_classification.py`, `skills/tests/merge-pull-requests/test_stage_routing.py`, `skills/tests/merge-pull-requests/fixtures/jcs-unicode-golden.json`

- [ ] 3.6 (M) Implement one shared JCS digest helper plus lock/reload/reclassify disposition, schema-valid locked initialization of missing legacy `operator_override_history` to `[]`, and atomic override-history append before execution-time invalidation
  **Dependencies**: 3.5
  **Files**: `skills/merge-pull-requests/scripts/pr_delivery.py`, `skills/merge-pull-requests/scripts/merge_plan.py`, `skills/merge-pull-requests/scripts/execute_merge_plan.py`

- [ ] 3.7 (M) Write stage-routing tests for PR-head validation, implementation gates, cleanup, archival, immutable discovery versus latest classification, and convergence
  **Spec scenarios**: `merge-pull-requests` — AC-02; AC-03; Proposal routing skips implementation-only gates; Implementation and mixed routing preserves cleanup; Durable merge plan preserves stage evidence on resume; Proposal OpenSpec PR is merged without cleanup recommendation; Legacy implementation PR retains cleanup behavior
  **Contracts**: `contracts/schemas/merge-plan-delivery-fields.schema.json`, `contracts/schemas/pr-delivery-classification.schema.json`
  **Design decisions**: D14-D15
  **Dependencies**: 3.6
  **Files**: `skills/tests/merge-pull-requests/test_stage_routing.py`, `skills/merge-pull-requests/scripts/tests/test_post_merge_cleanup.py`

- [ ] 3.8 (M) Route merge planning, validation, holdout, cleanup, plus archival by preserved delivery-stage evidence
  **Dependencies**: 3.4, 3.7
  **Files**: `skills/merge-pull-requests/SKILL.md`, `skills/merge-pull-requests/scripts/post_merge_cleanup.py`, `skills/merge-pull-requests/scripts/merge_plan.py`, `skills/merge-pull-requests/scripts/execute_merge_plan.py`

- [ ] 3.9 (S) Write merge sync-point and post-merge cleanup tests proving live leases and provisioning reservations block, while expired, retained-idle, and stale legacy state do not
  **Contracts**: `contracts/mutating-skill-inventory.yaml`, `contracts/schemas/worktree-registry-v2.schema.json`
  **Dependencies**: 1.6, 3.8
  **Files**: `skills/tests/merge-pull-requests/**`, `skills/merge-pull-requests/scripts/tests/test_post_merge_cleanup.py`

- [ ] 3.10 (S) Migrate merge-pull-requests and post-merge cleanup from direct pinned/heartbeat interpretation to the canonical shared sync-point guard
  **Dependencies**: 3.9
  **Files**: `skills/merge-pull-requests/SKILL.md`, `skills/merge-pull-requests/scripts/post_merge_cleanup.py`

## 4. Autopilot continuous ownership

- [ ] 4.1 (M) Write live/expired controller tests for fresh bootstrap, one stable owner plus exact lease/controller triple and generation, required null session identity, parent-only renewal, same-controller retry, replacement-controller resume, zombie rejection, and quarantine escalation
  **Spec scenarios**: `skill-workflow` — AC-07; Fresh description bootstraps before PLAN mutation; Replacement controller resumes without duplicating a live writer; Escalation checkpoints before releasing activity; `worktree` — Duplicate live controller cannot reuse the same fence; Expired writer is fenced after same-owner resume
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/autopilot-run-recovery.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D7, D9
  **Dependencies**: 1.4, 2.4
  **Files**: `skills/autopilot/scripts/tests/test_autopilot_lifecycle.py`, `skills/autopilot/scripts/tests/test_autopilot.py`

- [ ] 4.2 (M) Implement autopilot parent-controller ownership with `session_id=null`, exact-triple dispatch assertions, fenced resume, and checkpoint-before-teardown/quarantine finally behavior
  **Dependencies**: 4.1
  **Files**: `skills/autopilot/scripts/autopilot.py`

- [ ] 4.3 (M) Write external run-state tests for unsafe identifiers and derived-envelope mismatch before I/O, canonical change-id mismatch, truncated-envelope preservation, generation CAS/concurrent writers, stale-controller rejection, fsync/teardown faults, null-session hook no-op, identity-bound pending-to-removed and pending-to-quarantined CAS, replacement-lease conflicts, exact-tip exception/escalate resume, terminal removed+done refusal and finalization-only recovery, advanced/rewound/missing/URL-mismatched refusal, exact blob digest, canonical LoopState validation/migration, quarantine, generic-GC exclusion, 30-day dedicated-GC eligibility/locking/corruption, and partial-state reconciliation
  **Spec scenarios**: `skill-workflow` — Released or removed autopilot checkout resumes from durable state; Escalation checkpoints before releasing activity; Unsafe teardown projects quarantine through the prior fence; Completed removed autopilot run is terminal; Dedicated recovery GC retains terminal tombstones for 30 days
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/autopilot-run-recovery.schema.json`, `skills/autopilot/install_assets/openspec/schemas/convergence-state.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D9
  **Dependencies**: 4.2
  **Files**: `skills/autopilot/scripts/tests/test_autopilot_lifecycle.py`, `skills/autopilot/scripts/tests/test_autopilot_recovery.py`, `skills/autopilot/scripts/tests/test_autopilot.py`, `skills/tests/autopilot/test_loop_state.py`

- [ ] 4.4 (M) Implement convergence-state schema v5 save/load/migration, locked generation-CAS/fsync external envelope persistence, exact-tip exception/escalate recreation, terminal DONE tombstones, identity-bound pending-to-removed/quarantined reconciliation, and dedicated globally ordered 30-day recovery GC
  **Dependencies**: 4.3
  **Files**: `skills/autopilot/scripts/autopilot.py`, `skills/autopilot/install_assets/openspec/schemas/convergence-state.schema.json`, `skills/autopilot/references/worktree-lifecycle-recovery.md`

- [ ] 4.5 (S) Write dispatch-context tests proving nested phase agents inherit continuous lifecycle ownership and do not renew it
  **Spec scenarios**: `skill-workflow` — AC-07; Replacement controller resumes without duplicating a live writer
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D7, D9
  **Dependencies**: 4.2
  **Files**: `skills/tests/autopilot/test_phase_tasks.py`, `skills/tests/autopilot/test_build_phase_dispatch_kwargs.py`

- [ ] 4.6 (M) Propagate lifecycle context through phase dispatch; document continuous ownership and external-state recovery in autopilot
  **Dependencies**: 4.4, 4.5
  **Files**: `skills/autopilot/scripts/phase_agent.py`, `skills/autopilot/scripts/runner.py`, `skills/autopilot/SKILL.md`, `skills/autopilot/references/worktree-lifecycle-recovery.md`

- [ ] Checkpoint: run autopilot tests; inspect every terminal/resumed transition for stable owner identity plus checkpoint-before-teardown ordering.

## 5. Coordinator and UI projections

- [ ] 5.1 (M) Write coordinator source/container import-contract, API/SSE, kick recovery-matrix, TOCTOU generation, and projection tests for live, expired, retained, legacy, corrupt, all unfinished reservation blockers with expired reservations labeled for recovery, proposal-plan, immutable/latest classification, blocked ambiguity, valid override, invalidated override history/reason, and newly clear routing without stale controls
  **Spec scenarios**: `coordinator-kanban-viz` — Live lease is projected as active; AC-09; AC-08; AC-11; AC-02; Live continuous autopilot lease blocks sync points; Unfinished reservation blocks sync points without appearing active; Corrupt registry is an indeterminate blocker; Ambiguous delivery is operator-visible; Proposal plan omits archival action
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/merge-plan-delivery-fields.schema.json`
  **Design decisions**: D1, D15
  **Dependencies**: 1.4, 3.8
  **Files**: `agent-coordinator/tests/test_sync_points.py`, `agent-coordinator/tests/test_worktrees_view.py`, `agent-coordinator/tests/test_kanban_viz_endpoints.py`, `agent-coordinator/tests/test_coordination_api.py`, `agent-coordinator/tests/test_coordination_api_new_endpoints.py`, `agent-coordinator/tests/test_check_docker_imports.py`, `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py`

- [ ] 5.2 (M) Align coordinator sync-point, worktree, API/SSE, kick recovery dispatch, plus merge projections with canonical lifecycle/delivery evidence and ship the shared interpreter in the runtime image
  **Dependencies**: 5.1
  **Files**: `agent-coordinator/src/sync_points.py`, `agent-coordinator/src/worktrees_view.py`, `agent-coordinator/src/coordination_api.py`, `agent-coordinator/src/event_stream.py`, `agent-coordinator/src/openspec_proposals_api.py`, `agent-coordinator/src/kanban_viz.py`, `agent-coordinator/Dockerfile`

## 6. Canonical specifications, documentation, and integration

- [ ] 6.1 (M) Update canonical specs plus operator documentation for inspection, recovery, proposal delivery, plus stage-aware merging
  **Spec scenarios**: all scenarios in `worktree`, `skill-workflow`, `merge-pull-requests`, and `coordinator-kanban-viz`
  **Contracts**: all files under `contracts/`
  **Design decisions**: D1-D17
  **Dependencies**: 2.4, 2.6, 2.9, 3.10, 4.6, 5.2
  **Files**: `openspec/specs/worktree/spec.md`, `openspec/specs/skill-workflow/spec.md`, `openspec/specs/merge-pull-requests/spec.md`, `openspec/specs/coordinator-kanban-viz/spec.md`, `docs/guides/worktree-management.md`, `docs/guides/workflow.md`, `docs/mental-models.md`

- [ ] 6.2 (S) Regenerate runtime skill mirrors; run drift plus artifact validation
  **Spec scenarios**: `skill-workflow` — AC-12
  **Contracts**: all files under `contracts/`
  **Design decisions**: D16-D17
  **Dependencies**: 6.1
  **Files**: `skills/install.sh`, generated `.agents/skills/**`, generated `.claude/skills/**`, generated `openspec/schemas/convergence-state.schema.json`

- [ ] 6.3 (S) Write and implement the changed-Python quality helper that validates the recorded implementation diff base, unions committed/staged/unstaged/renamed/added/untracked NUL-delimited paths, excludes generated `.agents/skills/**` and `.claude/skills/**` Python mirrors only after byte-for-byte drift validation, routes every remaining existing Python file to the skills or coordinator environment, and runs Ruff check plus format-check without failing on unrelated baseline debt; test both exclusion and drift-failure behavior
  **Contracts**: `contracts/schemas/baseline-gates.schema.json`
  **Dependencies**: 6.2
  **Files**: `skills/validate-packages/scripts/ruff_changed_files.py`, `skills/validate-packages/scripts/tests/test_ruff_changed_files.py`

- [ ] 6.4 (M) Run direct-proposal, reviewed-implementation, autopilot exact-tip exception/escalate resume plus terminal-DONE refusal, identity-bound quarantine and recovery-GC, crash-expiry/zombie fencing, reservation expiry/replay/disposal faults, recovery-quarantine/audit, retention, legacy force-teardown, coordinator kick, inventory coverage, vendor-provenance, override history, fixed JCS fixture, convergence-schema parity, changed-file Ruff, mypy/static, mirror drift, and `git diff --check` verification
  **Spec scenarios**: AC-01 through AC-12
  **Contracts**: all files under `contracts/`
  **Design decisions**: D1-D17
  **Dependencies**: 6.3
  **Files**: `skills/tests/contracts/test_phase_scoped_worktree_contracts.py`, `skills/tests/contracts/fixtures/phase-scoped-worktree-lifecycle/**`, validation evidence under `openspec/changes/phase-scoped-worktree-lifecycle/`

- [ ] Checkpoint: run strict OpenSpec, package, architecture, pytest, formatting, static, mirror-drift, plus `git diff --check` gates.
