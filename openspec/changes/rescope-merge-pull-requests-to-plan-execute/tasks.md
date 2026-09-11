# Tasks: rescope-merge-pull-requests-to-plan-execute

Sizes per plan-feature sizing table. No XL tasks; none L.

## Phase 1 — Schema 1.1

- [x] 1.1 Write tests for merge-plan schema 1.1 — kind enum, change_id, remediation_skill, ci_failure_class, version const, 1.0 document rejected (S)
  **Spec scenarios**: merge-infrastructure.schema-1-1-kind-fields; merge-pull-requests Durable Merge Plan Artifact (analysis emits 1.1)
  **Contracts**: contracts/merge-plan.schema.json
  **Design decisions**: D7
  **Dependencies**: None
- [x] 1.2 Bump `skills/merge-pull-requests/contracts/merge-plan.schema.json` to 1.1 including definition plus live fields (S)
  **Design decisions**: D7
  **Dependencies**: 1.1
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Kind classification and plan builder

- [x] 2.1 Write tests for kind heuristic — plan-only prefix, implementation escape, automation origins, operator override wins over re-heuristic (M)
  **Spec scenarios**: merge-pull-requests.heuristic-plan-only, heuristic-implementation, operator-kind-override
  **Contracts**: contracts/merge-plan.schema.json
  **Design decisions**: D2
  **Dependencies**: 1.2
- [x] 2.2 Implement `classify_kind` persisting `kind`, `change_id`, `remediation_skill` from `build_plan` (M)
  **Design decisions**: D2
  **Dependencies**: 2.1
- [x] 2.3 Write tests for CI-failure class — transient vs pr_specific vs stale_base, operator-inserted runtime edge with inserted_reason (M)
  **Spec scenarios**: merge-pull-requests.stale-base-class-surfaced, operator-runtime-edge
  **Design decisions**: D8
  **Dependencies**: 1.2
- [x] 2.4 Wire CI-failure class into analysis output via the existing `amend_plan()` runtime-edge seam (S)
  **Design decisions**: D8
  **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.5 Write tests that `render_plan` surfaces kind, remediation_skill, plus ci_failure_class without mutating JSON (S)
  **Spec scenarios**: merge-infrastructure Rendered projection matches the authoritative JSON
  **Dependencies**: 2.2, 2.4
- [x] 2.6 Update `render_plan.py` for the 1.1 projection columns (S)
  **Dependencies**: 2.5
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Execute kernel

- [x] 3.1 Write tests for `_delegation_commands` — iterate-on-plan for kind=plan, iterate-on-implementation for kind=implementation, quick-task for non-OpenSpec comments, `--vendor-review` present, never iterate-on-plan for implementation (M)
  **Spec scenarios**: merge-pull-requests.plan-node-invokes-iterate-on-plan, impl-node-invokes-iterate-on-implementation; Merge Plan Comment-Addressing Seam
  **Design decisions**: D1, D3
  **Dependencies**: 1.2
- [x] 3.2 Route `_delegation_commands` from persisted kind / remediation_skill (S)
  **Design decisions**: D1
  **Dependencies**: 3.1
- [x] 3.3 Write tests for merge-time vendor_review skip when iterate consensus HEAD matches live PR head, fail-closed when consensus missing or stale (M)
  **Spec scenarios**: merge-pull-requests.skip-pr-diff-review-after-iterate, Eligible vendor review fails closed
  **Design decisions**: D3
  **Dependencies**: 1.2
- [x] 3.4 Implement the consensus-HEAD skip in `execute_plan` without weakening security or proposal_acceptance gates (M)
  **Design decisions**: D3
  **Dependencies**: 3.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.5 Write characterization tests that `execute_plan.py` has no git checkout/commit/push of the PR branch (S)
  **Spec scenarios**: merge-pull-requests Orchestrated Iterate Remediation (kernel SHALL NOT modify PR code)
  **Design decisions**: D1
  **Dependencies**: None
- [x] 3.6 Write tests for cheap-path — green automation merges without iterate or vendor_review; comments drop cheap path (M)
  **Spec scenarios**: merge-pull-requests.cheap-path-merges, cheap-path-dropped-on-comments
  **Design decisions**: D4
  **Dependencies**: 2.2
- [x] 3.7 Implement cheap-path execution policy in `execute_plan` (S)
  **Design decisions**: D4
  **Dependencies**: 3.6, 2.2

## Phase 4 — Conductor helper

- [x] 4.1 Write tests for `next_node` — topological ready set, skip in_progress/blocked, resume after last_merged_pr (M)
  **Spec scenarios**: merge-pull-requests.compact-after-merge, default-is-plan-then-execute
  **Design decisions**: D1, D5
  **Dependencies**: 1.2
- [x] 4.2 Implement `next_node.py` as a read-only plan helper (S)
  **Design decisions**: D1
  **Dependencies**: 4.1
- [x] 4.3 Write tests that iterate preconditions fail closed — approved plan node, unapproved implementation node (S)
  **Spec scenarios**: merge-pull-requests.wrong-iterate-precondition-halts
  **Design decisions**: D9
  **Dependencies**: 2.2
- [x] 4.4 Implement the precondition check used by the conductor before iterate dispatch (S)
  **Design decisions**: D9
  **Dependencies**: 4.3
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 5 — SKILL.md default path

- [x] 5.1 Rewrite the default SKILL.md path to analysis → discuss → persist → node loop; keep `--interactive` as the old per-PR menu (M)
  **Spec scenarios**: merge-pull-requests.default-is-plan-then-execute, interactive-opt-in, plan-approval-before-side-effects
  **Design decisions**: D1
  **Dependencies**: 2.2, 3.2, 4.2
- [x] 5.2 Document iterate invocation with `--vendor-review`, worktree isolation, plus fail-closed preconditions in the conductor steps (S)
  **Spec scenarios**: skill-workflow.merge-invokes-iterate, merge-iterate-always-vendor-review
  **Design decisions**: D3, D6, D9
  **Dependencies**: 5.1
- [x] 5.3 Document compact-after-merge, merge-plan.json resume, no autopilot loop-state, sync-point released around iterate, re-check guard before merge (S)
  **Spec scenarios**: merge-pull-requests.compact-after-merge, no-autopilot-loop-state, iterate-not-under-sync-point, recheck-guard-after-iterate
  **Design decisions**: D5, D6
  **Dependencies**: 5.1
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Spec purpose, integration, docs

- [x] 6.1 Set `openspec/specs/merge-pull-requests/spec.md` Purpose from TBD to the plan-then-execute conductor (S)
  **Dependencies**: 5.1
- [x] 6.2 Write integration tests covering one plan node + one implementation node + one cheap-path node through classify → next_node → delegation → cheap-path merge stub (M)
  **Spec scenarios**: merge-pull-requests.heuristic-plan-only, impl-node-invokes-iterate-on-implementation, cheap-path-merges
  **Contracts**: contracts/merge-plan.schema.json
  **Design decisions**: D1, D2, D4
  **Dependencies**: 3.7, 4.2, 4.4
- [x] 6.3 Update merge-log template in SKILL.md for kind, remediations, disagreements, plan revision (S)
  **Spec scenarios**: skill-workflow Merge Log Artifact
  **Dependencies**: 5.1
- [x] Checkpoint: run tests, review diff, verify scope
