# Plan review: add-supervisor-candidate-work-digest

Review these read-only OpenSpec plan artifacts in the current working directory:

- `openspec/changes/add-supervisor-candidate-work-digest/proposal.md`
- `openspec/changes/add-supervisor-candidate-work-digest/design.md`
- `openspec/changes/add-supervisor-candidate-work-digest/tasks.md`
- `openspec/changes/add-supervisor-candidate-work-digest/specs/supervise/spec.md`
- `openspec/changes/add-supervisor-candidate-work-digest/contracts/`
- `openspec/changes/add-supervisor-candidate-work-digest/work-packages.yaml`
- `openspec/changes/add-supervisor-candidate-work-digest/plan-findings.md`

Evaluate correctness, completeness, testability, contract consistency, architecture,
security, performance, observability, resilience, compatibility, and work-package DAG/
scope validity. Inspect existing repository code and consumed contracts where needed.
Pay particular attention to bounded rubric dispatch, scorer timestamps, partial batch
failure, the host/script boundary for sanitized evidence preparation, dry-run behavior,
fingerprint/cache interactions, and roadmap transaction safety.

Output only valid JSON conforming to
`openspec/schemas/review-findings.schema.json`, with this shape:

```json
{
  "review_type": "plan",
  "target": "add-supervisor-candidate-work-digest",
  "reviewer_vendor": "<your vendor>",
  "findings": []
}
```

Every finding must include `id`, `type`, `criticality`, `description`, `resolution`,
`disposition`, `axis`, and `severity`. Use only schema enum values. Prefix descriptions
exactly according to severity: `Critical:`, `Nit:`, `Optional:`, or `FYI:`; a positive
`severity: none` observation has no prefix. Use `critical` severity only for issues that
must be fixed before implementation, with `disposition: fix` or `escalate`. Use
`nit` with `fix`, and `optional`/`fyi`/`none` with `accept`. Include real `file_path`
and `line_range` evidence. Do not edit any file.
