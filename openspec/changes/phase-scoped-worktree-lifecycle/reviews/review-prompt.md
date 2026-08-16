# Independent plan review: phase-scoped-worktree-lifecycle

Review the following artifacts as read-only inputs:

- `openspec/changes/phase-scoped-worktree-lifecycle/proposal.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/design.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/tasks.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/specs/**/spec.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/contracts/**`
- `openspec/changes/phase-scoped-worktree-lifecycle/work-packages.yaml`

Evaluate specification completeness, contract consistency, architecture,
correctness, security, performance, observability, compatibility, resilience,
and work-package validity. Pay special attention to crash recovery, lease
fencing, v1-to-v2 migration, unsafe checkout adoption, delivery-stage routing,
cross-change prerequisites, package scopes, and package-level verification.

Output only one JSON object conforming to
`openspec/schemas/review-findings.schema.json` with:

- `review_type`: `plan`
- `target`: `phase-scoped-worktree-lifecycle`
- a populated `reviewer_vendor`
- findings that include every required field: `id`, `type`, `criticality`,
  `description`, `disposition`, `axis`, and `severity`

Every description must begin with the prefix matching severity: `Critical:`,
`Nit:`, `Optional:`, or `FYI:`. A `none` positive observation uses no prefix.
Use coherent dispositions: critical/nit findings normally use `fix`, optional
and FYI findings use `accept`, and positive observations use `accept`. Split
different issues into separate findings. Do not modify the plan artifacts.
