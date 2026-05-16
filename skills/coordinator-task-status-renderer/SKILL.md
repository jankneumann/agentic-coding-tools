---
name: coordinator-task-status-renderer
description: "Render and seed coordinator-owned task status block in OpenSpec tasks.md"
category: OpenSpec
tags: [openspec, coordinator, tasks, hook]
user_invocable: false
triggers:
  - "render task status"
  - "seed tasks from md"
related:
  - plan-feature
  - implement-feature
  - coordination-bridge
---

# Coordinator Task Status Renderer

Two scripts ship with this skill:

- `scripts/render_tasks_status.py <change-id>` — read coordinator issue state for
  the change and rewrite the managed block in `openspec/changes/<change-id>/tasks.md`.
- `scripts/seed_tasks_from_md.py <change-id>` — parse hand-authored tasks from
  `tasks.md` and POST them to the coordinator as issues. Idempotent on the
  `(change:<id>, task:<key>)` label pair.

Invocation contracts and managed-block format: see
`openspec/changes/add-coordinator-task-status-renderer/contracts/README.md`.

This skill is not user-invocable. It is wired into:

- `.githooks/pre-commit` and `.githooks/post-merge` (calls renderer when
  `openspec/changes/<id>/tasks.md` is staged or merged).
- `/plan-feature` Gate 2 Approve (calls seeder once tasks.md is approved).
- `/implement-feature` start (seeding-retry on empty change-id, per D11).

Tests live at `skills/tests/coordinator-task-status-renderer/`.
