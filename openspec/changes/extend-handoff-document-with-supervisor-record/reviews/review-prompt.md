# Independent plan review: extend-handoff-document-with-supervisor-record

Review the OpenSpec plan at `openspec/changes/extend-handoff-document-with-supervisor-record/` as read-only input. Read all of:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/**/spec.md`
- `contracts/**`
- `work-packages.yaml`

Evaluate specification completeness, contract consistency, architecture alignment, security, performance, observability, resilience, compatibility, and work-package validity. Check the plan against the existing repository implementation and conventions where relevant. Pay particular attention to backward compatibility of the PostgreSQL RPC overload replacement, supervisor-only retrieval across every named surface, deterministic derivation and mirror idempotency, malformed-state handling, schema/runtime-validation ownership, and package dependency/scope correctness.

Output only one JSON object conforming to `openspec/schemas/review-findings.schema.json` with:

- `review_type`: `"plan"`
- `target`: `"extend-handoff-document-with-supervisor-record"`
- `reviewer_vendor`: your vendor/model name
- `findings`: an array of structured findings

Every finding must include `id`, `type`, `criticality`, `description`, `disposition`, `axis`, and `severity`. Use exactly one of the eight allowed axes. The description must begin with the marker matching severity: `Critical:`, `Nit:`, `Optional:`, or `FYI:`; positive observations use `severity: "none"` and need no marker. Keep severity/disposition coherent: critical or nit findings use `fix`; optional/FYI/none use `accept`; use `escalate` only when a human decision is genuinely required. Include `resolution`, `file_path`, and `line_range` when useful. Split distinct issues into separate findings. If no defects remain, emit at least two `severity: "none"` positive observations on different axes to demonstrate that the review completed.
