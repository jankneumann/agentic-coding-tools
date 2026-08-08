Review the OpenSpec plan for change `harden-review-consensus-and-recovery` as an independent, adversarial code-plan reviewer.

Read these artifacts from the current repository:

- `openspec/changes/harden-review-consensus-and-recovery/proposal.md`
- `openspec/changes/harden-review-consensus-and-recovery/design.md`
- `openspec/changes/harden-review-consensus-and-recovery/tasks.md`
- `openspec/changes/harden-review-consensus-and-recovery/specs/**/spec.md`
- `openspec/changes/harden-review-consensus-and-recovery/contracts/**`
- `openspec/changes/harden-review-consensus-and-recovery/work-packages.yaml`
- relevant existing implementation and schemas needed to assess feasibility

Evaluate correctness, security, performance, architecture, compatibility, resilience, observability, contract consistency, and package DAG/scope validity. Pay special attention to false quorum, one-vendor/one-vote invariants, replacement-vendor scheduling, attribution of terminal results, preservation of every source disposition, accepted-risk trust validation, output bounds, and whether every required task file is writable and verified by its owning package.

Output ONLY one valid JSON object conforming to `openspec/schemas/review-findings.schema.json`. Set `review_type` to `plan`, `target` to `harden-review-consensus-and-recovery`, and populate `reviewer_vendor`. Every finding must include `id`, `type`, `criticality`, `description`, `resolution`, `disposition`, `axis`, and `severity`; include `file_path` and `line_range` when possible. The description must start with the prefix matching severity (`Critical:`, `Nit:`, `Optional:`, or `FYI:`); severity `none` uses no prefix. Use disposition `fix` for critical/nit findings and `accept` for optional/fyi/none findings. Do not include markdown fences or prose outside the JSON.
