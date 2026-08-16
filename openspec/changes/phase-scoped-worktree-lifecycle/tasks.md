# Tasks: phase-scoped-worktree-lifecycle

All tasks use test-first ordering. Sizes describe one focused agent session; no task is XL and no task is L.

## 0. Enforced baseline gates

- [ ] 0.1 Record the merged baseline SHA for `add-merge-plan-orchestration`, rebase this branch, and validate that its file-tier merge-plan schema is the one extended here before dispatching package `wp-pr-delivery`
- [ ] 0.2 Record the merged baseline SHA for `validate-feature-findings-gate`, rebase this branch, and validate that its ephemeral validation worktree is the one wrapped here before dispatching package `wp-phase-lifecycle`

These are no-dispatch prerequisites, not advisory notes. If either active change
has not landed, the dependent package remains blocked rather than writing shared
paths concurrently.

## 1. Registry and activity-guard contract

- [ ] 1.1 (M) Write deterministic registry-v2 contract fixtures and lease tests covering migration, locking, session release, fencing, recovery quarantine, atomic disposal, remote reachability, retention, inspection, corruption, plus isolation
  **Spec scenarios**: `worktree` — Owner acquires and renews the default lease; Different owner cannot renew or release a live lease; Expired writer is fenced after same-owner resume; Matching release is idempotent; AC-08; Expired takeover quarantines unknown work; Clean durable expired takeover uses a new fence; AC-09; AC-11; Concurrent lifecycle updates preserve both owners' records; Inspection reports lifecycle categories without mutation; Pushed proposal branch is safely disposable before merge; Unsafe finalization quarantines recovery state; Acquire cannot race owner-checked disposal; Fresh legacy heartbeat maps every canonical lease field; Missing or invalid legacy heartbeat is diagnosable and idle; Corrupt registry blocks safety decisions without rewrite; Activity lease commands respect environment isolation
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D1-D6
  **Dependencies**: None
  **Files**: `skills/worktree/scripts/tests/test_worktree.py`, `skills/worktree/scripts/tests/test_environment_aware.py`, `skills/shared/tests/test_worktree_lifecycle.py`, `skills/tests/worktree/test_setup_prototype.py`, `skills/tests/worktree/fixtures/**`

- [ ] 1.2 (M) Implement the portable locked schema-v2 interpreter, fenced retention/lease/recovery/disposal CLI operations, and source/install import boundary
  **Dependencies**: 1.1
  **Files**: `skills/shared/worktree_lifecycle.py`, `skills/worktree/scripts/worktree.py`, `skills/worktree/SKILL.md`

- [ ] 1.3 (S) Write active-agent guard tests for live, released, expired, retained, legacy, malformed, plus corrupt entries
  **Spec scenarios**: `worktree` — AC-08, AC-09, AC-11, Corrupt registry blocks safety decisions without rewrite; `coordinator-kanban-viz` — AC-02
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`
  **Design decisions**: D1-D6
  **Dependencies**: 1.1
  **Files**: `skills/shared/tests/test_active_agents.py`

- [ ] 1.4 (S) Make the local active-agent guard block only current activity evidence
  **Dependencies**: 1.2, 1.3
  **Files**: `skills/shared/active_agents.py`

- [ ] Checkpoint: run worktree plus shared guard tests; inspect the cumulative diff; verify package scope plus migration safety.

## 2. Standalone phase lifecycle and session backstop

- [ ] 2.1 (M) Write process-level lifecycle-controller and workflow contract tests for proposal branches, durable pushes, strict validation, renewal loss, fencing assertions, atomic disposal/quarantine, all-tier finalization, plus continuous-owner nesting
  **Spec scenarios**: `skill-workflow` — Durable push precedes phase release; Failed phase still finalizes activity; AC-01; Proposal artifacts fail strict validation; AC-06; Later phase recreates from durable remote state; `worktree` — Expired writer is fenced after same-owner resume; Unsafe finalization quarantines recovery state; Acquire cannot race owner-checked disposal
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`, `contracts/schemas/worktree-registry-v2.schema.json`
  **Design decisions**: D7-D8
  **Dependencies**: 1.2, 1.4
  **Files**: `skills/shared/tests/test_phase_lifecycle.py`, `skills/tests/plan-feature/test_skill_contract.py`, `skills/tests/implement-feature/test_skill_contract.py`, `skills/tests/iterate-on-plan/test_skill_contract.py`, `skills/tests/iterate-on-implementation/test_skill_contract.py`, `skills/tests/validate-feature/test_skill_contract.py`

- [ ] 2.2 (M) Implement the executable renew/assert/finalize controller and add standalone/continuous lifecycle modes plus PR provenance trailers to planning, implementation, iteration, and validation skills
  **Dependencies**: 2.1
  **Files**: `skills/shared/phase_lifecycle.py`, `skills/plan-feature/SKILL.md`, `skills/implement-feature/SKILL.md`, `skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`, `skills/validate-feature/SKILL.md`

- [ ] 2.3 (S) Write session-finalization tests for exact owner/session release, preserved-checkout quarantine, and absent-entry idempotency without coordinator connectivity
  **Spec scenarios**: `skill-workflow` — Session end releases only matching owners; `worktree` — Different owner cannot renew or release a live lease; Unsafe finalization quarantines recovery state
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D5, D10
  **Dependencies**: 1.2
  **Files**: `skills/tests/session-bootstrap/test_deregister_agent.py`, `agent-coordinator/tests/test_install_hooks.py`

- [ ] 2.4 (S) Add best-effort local lease release to shipped session hooks
  **Dependencies**: 2.3
  **Files**: `skills/session-bootstrap/scripts/hooks/deregister_agent.py`, `skills/session-bootstrap/SKILL.md`, `agent-coordinator/scripts/deregister_agent.py`, `agent-coordinator/scripts/install_hooks.py`

- [ ] Checkpoint: run lifecycle skill plus session-hook tests; verify every exit path releases only its owner after durable output.

## 3. Pull-request delivery classification and merge routing

- [ ] 3.1 (M) Write exhaustive truth-table and schema-fixture tests for proposal, implementation-with-plan-refinement, mixed-without-base-plan, legacy, unknown paths, conflicting/duplicate/invalid/missing markers, truncated diffs, failed base/head inspection, plus immutable base/head SHAs
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

- [ ] 3.5 (M) Write routing tests for PR-head validation, implementation gates, ambiguity, immutable discovery versus latest classification, auditable operator disposition, cleanup, archival, plus convergence
  **Spec scenarios**: `merge-pull-requests` — AC-02; AC-03; Proposal routing skips implementation-only gates; Implementation and mixed routing preserves cleanup; Durable merge plan preserves stage evidence on resume; Operator disposition is explicit and auditable; Proposal OpenSpec PR is merged without cleanup recommendation; Legacy implementation PR retains cleanup behavior
  **Contracts**: `contracts/schemas/merge-plan-delivery-fields.schema.json`, `contracts/schemas/pr-delivery-classification.schema.json`
  **Design decisions**: D14-D15
  **Dependencies**: 3.2
  **Files**: `skills/tests/merge-pull-requests/test_stage_routing.py`, `skills/merge-pull-requests/scripts/tests/test_post_merge_cleanup.py`

- [ ] 3.6 (M) Route merge planning, validation, holdout, cleanup, plus archival by preserved delivery-stage evidence
  **Dependencies**: 3.4, 3.5
  **Files**: `skills/merge-pull-requests/SKILL.md`, `skills/merge-pull-requests/scripts/post_merge_cleanup.py`, `skills/merge-pull-requests/scripts/merge_plan.py`, `skills/merge-pull-requests/scripts/execute_merge_plan.py`

## 4. Autopilot continuous ownership

- [ ] 4.1 (M) Write loop-state lifecycle tests for fresh-description change-id/worktree bootstrap, one owner plus fenced lease id, renewal, expired resume, zombie rejection, quarantine escalation, exception finalization, plus pre-DONE release
  **Spec scenarios**: `skill-workflow` — AC-07; Fresh description bootstraps before PLAN mutation; Resume renews rather than reacquires under another owner; Escalation checkpoints before releasing activity; `worktree` — Expired writer is fenced after same-owner resume
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D7, D9
  **Dependencies**: 1.2
  **Files**: `skills/autopilot/scripts/tests/test_autopilot_lifecycle.py`, `skills/autopilot/scripts/tests/test_autopilot.py`

- [ ] 4.2 (M) Persist the autopilot run owner with acquire, renew, checkpointed release, plus finally behavior
  **Dependencies**: 4.1
  **Files**: `skills/autopilot/scripts/autopilot.py`

- [ ] 4.3 (S) Write dispatch-context tests proving nested phase agents inherit continuous lifecycle ownership
  **Spec scenarios**: `skill-workflow` — AC-07; Resume renews rather than reacquires under another owner
  **Contracts**: `contracts/cli/worktree-lifecycle.yaml`
  **Design decisions**: D7, D9
  **Dependencies**: 4.1
  **Files**: `skills/tests/autopilot/test_phase_tasks.py`, `skills/tests/autopilot/test_build_phase_dispatch_kwargs.py`

- [ ] 4.4 (M) Propagate lifecycle context through phase dispatch; document continuous ownership in autopilot
  **Dependencies**: 4.2, 4.3
  **Files**: `skills/autopilot/scripts/phase_agent.py`, `skills/autopilot/scripts/runner.py`, `skills/autopilot/SKILL.md`, `skills/autopilot/references/worktree-lifecycle-recovery.md`

- [ ] Checkpoint: run autopilot tests; inspect every terminal/resumed transition for stable owner identity plus checkpoint-before-release ordering.

## 5. Coordinator and UI projections

- [ ] 5.1 (M) Write coordinator source/container import-contract and projection tests for live, expired, retained, legacy, corrupt, proposal-plan, immutable/latest classification, plus ambiguous delivery records
  **Spec scenarios**: `coordinator-kanban-viz` — Live lease is projected as active; AC-09; AC-08; AC-11; AC-02; Live continuous autopilot lease blocks sync points; Corrupt registry is an indeterminate blocker; Ambiguous delivery is operator-visible; Proposal plan omits archival action
  **Contracts**: `contracts/schemas/worktree-registry-v2.schema.json`, `contracts/schemas/merge-plan-delivery-fields.schema.json`
  **Design decisions**: D1, D15
  **Dependencies**: 1.2, 3.2
  **Files**: `agent-coordinator/tests/test_sync_points.py`, `agent-coordinator/tests/test_worktrees_view.py`, `agent-coordinator/tests/test_kanban_viz_endpoints.py`, `agent-coordinator/tests/test_check_docker_imports.py`, `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py`

- [ ] 5.2 (M) Align coordinator sync-point, worktree, plus merge projections with canonical lifecycle/delivery evidence and ship the shared interpreter in the runtime image
  **Dependencies**: 5.1
  **Files**: `agent-coordinator/src/sync_points.py`, `agent-coordinator/src/worktrees_view.py`, `agent-coordinator/src/openspec_proposals_api.py`, `agent-coordinator/src/kanban_viz.py`, `agent-coordinator/Dockerfile`

## 6. Canonical specifications, documentation, and integration

- [ ] 6.1 (M) Update canonical specs plus operator documentation for inspection, recovery, proposal delivery, plus stage-aware merging
  **Spec scenarios**: all scenarios in `worktree`, `skill-workflow`, `merge-pull-requests`, and `coordinator-kanban-viz`
  **Contracts**: all files under `contracts/`
  **Design decisions**: D1-D17
  **Dependencies**: 2.2, 2.4, 3.6, 4.4, 5.2
  **Files**: `openspec/specs/worktree/spec.md`, `openspec/specs/skill-workflow/spec.md`, `openspec/specs/merge-pull-requests/spec.md`, `openspec/specs/coordinator-kanban-viz/spec.md`, `docs/guides/worktree-management.md`, `docs/guides/workflow.md`, `docs/mental-models.md`

- [ ] 6.2 (S) Regenerate runtime skill mirrors; run drift plus artifact validation
  **Spec scenarios**: `skill-workflow` — AC-12
  **Contracts**: all files under `contracts/`
  **Design decisions**: D16-D17
  **Dependencies**: 6.1
  **Files**: `skills/install.sh`, generated `.agents/skills/**`, generated `.claude/skills/**`

- [ ] 6.3 (M) Run direct-proposal, reviewed-implementation, autopilot, crash-expiry/zombie fencing, atomic-disposal, recovery-quarantine, retention, legacy/corrupt-registry, vendor-provenance, plus ambiguity verification; run representative schema instances with reference resolution and format checking, full targeted pytest, Ruff, mypy/static checks, mirror drift, and `git diff --check`
  **Spec scenarios**: AC-01 through AC-12
  **Contracts**: all files under `contracts/`
  **Design decisions**: D1-D17
  **Dependencies**: 6.2
  **Files**: `skills/tests/contracts/test_phase_scoped_worktree_contracts.py`, `skills/tests/contracts/fixtures/phase-scoped-worktree-lifecycle/**`, validation evidence under `openspec/changes/phase-scoped-worktree-lifecycle/`

- [ ] Checkpoint: run strict OpenSpec, package, architecture, pytest, formatting, static, mirror-drift, plus `git diff --check` gates.
