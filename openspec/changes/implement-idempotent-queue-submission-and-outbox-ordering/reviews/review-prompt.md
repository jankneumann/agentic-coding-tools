Review the OpenSpec plan for change `implement-idempotent-queue-submission-and-outbox-ordering` as an independent senior architect and code reviewer.

Read these artifacts in the repository worktree:

- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/proposal.md`
- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/design.md`
- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/tasks.md`
- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/specs/**/spec.md`
- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/contracts/**`
- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/work-packages.yaml`

Also inspect the existing queue, HTTP/MCP/CLI, coordination bridge, and autopilot implementation where needed to test feasibility and compatibility. Evaluate correctness, architecture, security, performance, observability, resilience, compatibility, contract consistency, migration safety, concurrency behavior, and executable verification coverage. Pay particular attention to both possible serialization orders when keyed submit races reconciliation for different transition sequences.

Output only one JSON object conforming to `openspec/schemas/review-findings.schema.json`. Set `review_type` to `plan`, `target` to the change id, and `reviewer_vendor` to your vendor/model identity. Every finding must include `id`, `type`, `criticality`, `description`, `disposition`, `axis`, and `severity`; include precise `file_path`, `line_range`, and `resolution` when applicable. `description` must start with the exact marker matching severity (`Critical:`, `Nit:`, `Optional:`, `FYI:`); positive `none` findings need no marker. Critical findings must use `disposition: fix` or `escalate`. Do not edit any plan artifact.
