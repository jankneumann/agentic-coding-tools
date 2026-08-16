# Independent plan review: phase-scoped-worktree-lifecycle

Review the following artifacts as read-only input:

- `openspec/changes/phase-scoped-worktree-lifecycle/proposal.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/design.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/tasks.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/specs/**/spec.md`
- `openspec/changes/phase-scoped-worktree-lifecycle/contracts/**`
- `openspec/changes/phase-scoped-worktree-lifecycle/work-packages.yaml`

Evaluate specification completeness, contract consistency, architecture, security, performance, observability, compatibility, resilience, and work-package validity. Pay special attention to active-writer fencing, crash/recovery transitions, migration, durable-ref proof, PR-stage routing, and resume behavior.

Output only one JSON object conforming to `openspec/schemas/review-findings.schema.json`. Set `review_type` to `plan`, `target` to `phase-scoped-worktree-lifecycle`, and populate `reviewer_vendor`. Every finding must include `id`, `type`, `criticality`, `axis`, `severity`, `description`, `resolution`, and `disposition`; each description must start with the marker matching severity (`Critical:`, `Nit:`, `Optional:`, or `FYI:`), except `none` positive observations, which use no prefix. Critical and nit findings use disposition `fix`; optional/fyi/none use `accept`. Include accurate file paths and line ranges when available. Do not emit Markdown or commentary around the JSON.
