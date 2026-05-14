# Tasks — add-coordinator-task-status-renderer

> **Bootstrap note:** this change's own `tasks.md` will not have a renderer-managed block during implementation (the renderer doesn't exist yet). Implementers should follow existing `/implement-feature` discipline (per-commit checkbox flips) for this change. Future changes will get the managed block automatically from Gate 2 forward.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Document renderer CLI invocation contract in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.1 (block reflects state), .4 (markers absent)
  **Design decisions**: D6 (per-change-id invocation)
  **Dependencies**: None
  **Size**: S

- [ ] 1.2 Document seeder CLI invocation contract in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.7 (seeding), .8 (idempotency), .9 (coordinator-unreachable seeding)
  **Design decisions**: D3 (seed at Gate 2), D7 (task_key as primary key)
  **Dependencies**: 1.1
  **Size**: S

- [ ] 1.3 Document managed-block format and marker name in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.1, .2 (hand-content preservation)
  **Design decisions**: D1 (reuse plan-roadmap markers)
  **Dependencies**: 1.1
  **Size**: XS

- [ ] 1.4 Checkpoint: run `openspec validate add-coordinator-task-status-renderer --strict`, review contracts/README.md against spec scenarios
  **Dependencies**: 1.1, 1.2, 1.3

## Phase 2 — Renderer skill (wp-renderer-skill)

- [ ] 2.1 Write test: managed-block insertion when absent
  **Spec scenarios**: coordinator-task-status-renderer.4 (markers absent — renderer inserts)
  **Contracts**: contracts/README.md (managed-block format)
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.2 Write test: managed-block replacement preserves hand-content
  **Spec scenarios**: coordinator-task-status-renderer.2 (hand-authored content preserved)
  **Contracts**: contracts/README.md
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.3 Write test: renderer is idempotent on re-run
  **Spec scenarios**: coordinator-task-status-renderer.3 (re-render idempotent)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.4 Write test: stale-marker inserted on coordinator failure
  **Spec scenarios**: coordinator-task-status-renderer.5 (stale marker), .6 (recovery)
  **Design decisions**: D4 (stale-marker fallback)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.5 Checkpoint: run `pytest skills/tests/coordinator-task-status-renderer/test_render*.py` — confirm tests RED
  **Dependencies**: 2.1, 2.2, 2.3, 2.4

- [ ] 2.6 Implement `skills/coordinator-task-status-renderer/scripts/render_tasks_status.py` using `try_issue_list` and managed-block helpers from `plan-roadmap/scripts/renderer.py`
  **Spec scenarios**: coordinator-task-status-renderer.1, .2, .3, .4, .5, .6
  **Design decisions**: D1, D4, D5 (labels-based filtering), D6
  **Dependencies**: 2.5
  **Size**: M

- [ ] 2.7 Confirm tests 2.1–2.4 are GREEN
  **Dependencies**: 2.6
  **Size**: XS

- [ ] 2.8 Write test: seeder POSTs correct labels and metadata per task
  **Spec scenarios**: coordinator-task-status-renderer.7 (issues created)
  **Contracts**: contracts/README.md (seeder CLI)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.9 Write test: seeder is idempotent on `(change_id, task_key)`
  **Spec scenarios**: coordinator-task-status-renderer.8 (re-run after partial seeding)
  **Design decisions**: D3, D7
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.10 Write test: seeder logs warning but exits success when coordinator unreachable
  **Spec scenarios**: coordinator-task-status-renderer.9 (unreachable at Gate 2)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.11 Checkpoint: confirm seeder tests RED
  **Dependencies**: 2.8, 2.9, 2.10

- [ ] 2.12 Implement `skills/coordinator-task-status-renderer/scripts/seed_tasks_from_md.py` using coordination_bridge HTTP helpers
  **Spec scenarios**: coordinator-task-status-renderer.7, .8, .9
  **Design decisions**: D3, D7
  **Dependencies**: 2.11
  **Size**: M

- [ ] 2.13 Confirm tests 2.8–2.10 are GREEN
  **Dependencies**: 2.12
  **Size**: XS

- [ ] 2.14 Write `skills/coordinator-task-status-renderer/SKILL.md` with frontmatter (`user_invocable: false`, triggers, related skills)
  **Spec scenarios**: coordinator-task-status-renderer.10 (skill auto-installed), .11 (tests excluded)
  **Dependencies**: 2.7, 2.13
  **Size**: S

- [ ] 2.15 Checkpoint: run `bash skills/install.sh --mode rsync --deps none --python-tools none` and verify skill appears in `.claude/skills/` and `.agents/skills/`; confirm `skills/tests/` is excluded
  **Dependencies**: 2.14

## Phase 3 — Plan-feature integration (wp-plan-feature-integration)

- [ ] 3.1 Write test: `/plan-feature` Gate 2 approval triggers seeder for the change-id
  **Spec scenarios**: coordinator-task-status-renderer.7
  **Contracts**: contracts/README.md (seeder CLI)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 3.2 Write test: Gate 2 re-approval does not duplicate issues
  **Spec scenarios**: coordinator-task-status-renderer.8
  **Dependencies**: 1.4
  **Size**: S

- [ ] 3.3 Checkpoint: confirm plan-feature integration tests RED
  **Dependencies**: 3.1, 3.2

- [ ] 3.4 Edit `skills/plan-feature/SKILL.md` Step 12 to invoke seeder on "Approve" selection
  **Spec scenarios**: coordinator-task-status-renderer.7, .8
  **Design decisions**: D3
  **Dependencies**: 3.3
  **Size**: S

- [ ] 3.5 Confirm tests 3.1–3.2 are GREEN
  **Dependencies**: 3.4
  **Size**: XS

## Phase 4 — Hook wiring (wp-hooks)

- [ ] 4.1 Write test: pre-commit invokes renderer when `openspec/changes/<id>/tasks.md` is staged
  **Spec scenarios**: coordinator-task-status-renderer.12 (pre-commit fires on staged tasks.md)
  **Design decisions**: D2 (both hooks)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.2 Write test: pre-commit re-stages the rendered file
  **Spec scenarios**: coordinator-task-status-renderer.12
  **Design decisions**: D2 (auto-staging follows ruff pattern)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.3 Write test: pre-commit skips renderer when no tasks.md staged
  **Spec scenarios**: coordinator-task-status-renderer.13 (unrelated commit untouched)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.4 Checkpoint: confirm pre-commit tests RED
  **Dependencies**: 4.1, 4.2, 4.3

- [ ] 4.5 Edit `.githooks/pre-commit` to detect staged tasks.md paths, invoke renderer, re-stage
  **Spec scenarios**: coordinator-task-status-renderer.12, .13, .14 (renderer failure non-blocking)
  **Design decisions**: D2
  **Dependencies**: 4.4
  **Size**: S

- [ ] 4.6 Confirm pre-commit tests 4.1–4.3 are GREEN
  **Dependencies**: 4.5
  **Size**: XS

- [ ] 4.7 Write test: post-merge invokes renderer when merge touched tasks.md
  **Spec scenarios**: coordinator-task-status-renderer.15 (post-merge fires on merged tasks.md)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.8 Write test: post-merge skips renderer when merge did not touch tasks.md
  **Spec scenarios**: coordinator-task-status-renderer.16 (post-merge no-touch case)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.9 Checkpoint: confirm post-merge tests RED
  **Dependencies**: 4.7, 4.8

- [ ] 4.10 Edit `.githooks/post-merge` (currently no-op stub) to detect merged tasks.md paths and invoke renderer
  **Spec scenarios**: coordinator-task-status-renderer.15, .16
  **Design decisions**: D2
  **Dependencies**: 4.9
  **Size**: S

- [ ] 4.11 Confirm post-merge tests 4.7–4.8 are GREEN
  **Dependencies**: 4.10
  **Size**: XS

## Phase 5 — Integration and documentation (wp-integration)

- [ ] 5.1 Write end-to-end test: seed via plan-feature → modify coordinator state → commit triggers render → tasks.md reflects current state
  **Spec scenarios**: composite (all coordinator-task-status-renderer scenarios in a single flow)
  **Dependencies**: 2.15, 3.5, 4.6, 4.11
  **Size**: M

- [ ] 5.2 Confirm end-to-end test GREEN
  **Dependencies**: 5.1
  **Size**: XS

- [ ] 5.3 Update `docs/skills-catalogue.md` with `coordinator-task-status-renderer` entry
  **Dependencies**: 5.2
  **Size**: XS

- [ ] 5.4 Update `CLAUDE.md` "Workflow" section if appropriate (note that tasks.md status blocks are coordinator-rendered)
  **Dependencies**: 5.2
  **Size**: XS

- [ ] 5.5 Final checkpoint: run full skill test suite, verify `openspec validate add-coordinator-task-status-renderer --strict` passes, run `python3 skills/validate-packages/scripts/validate_work_packages.py openspec/changes/add-coordinator-task-status-renderer/work-packages.yaml`
  **Dependencies**: 5.3, 5.4
