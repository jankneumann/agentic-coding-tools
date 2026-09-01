# IMPL_REVIEW — extend-handoff-document-with-supervisor-record

Review commit `0ef9da84339c3cc7f34f77b368d3a78efe3e124f` on branch
`openspec/extend-handoff-document-with-supervisor-record` against `origin/main`.
This is a read-only review: do not modify files, commit, or push.

Read these requirements before reviewing:

- `openspec/changes/extend-handoff-document-with-supervisor-record/proposal.md`
- `openspec/changes/extend-handoff-document-with-supervisor-record/design.md`
- `openspec/changes/extend-handoff-document-with-supervisor-record/tasks.md`
- `openspec/changes/extend-handoff-document-with-supervisor-record/work-packages.yaml`
- `openspec/changes/extend-handoff-document-with-supervisor-record/specs/**/spec.md`
- `openspec/changes/extend-handoff-document-with-supervisor-record/contracts/**`

Inspect the complete diff with `git diff origin/main...0ef9da84`, including tests.
Review correctness, security, performance, compatibility, resilience,
observability, readability, architecture, work-package scope, contract adherence,
and backward compatibility. Pay particular attention to:

- Postgres overload replacement, argument order/defaults, JSONB round trips,
  and `supervisor_only` filtering.
- All coordinator/API/MCP/HTTP/CLI/help and host-bridge surfaces carrying the
  new optional field without changing ordinary handoffs.
- `cycle_state.py` derivation, prior-record normalization, timestamp selection,
  expiration, registry/roadmap ambiguity, repo-relative paths, mirror
  sanitization/idempotency, fingerprint exclusion, dry-run behavior, and audit.
- Canonical/runtime schemas staying aligned and rejecting invalid records.
- Whether tests genuinely exercise the stated WHEN/THEN requirements and
  failure paths rather than merely mirroring implementation details.

Return exactly one JSON object, with no markdown fences or prose, conforming to
`openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "implementation",
  "target": "whole-branch",
  "reviewer_vendor": "<your vendor>",
  "findings": [
    {
      "id": 1,
      "type": "correctness",
      "criticality": "high",
      "description": "Critical: precise issue and impact",
      "resolution": "specific corrective action",
      "disposition": "fix",
      "package_id": "<work-package id>",
      "file_path": "repo/relative/path.py",
      "line_range": {"start": 1, "end": 2},
      "axis": "correctness",
      "severity": "critical"
    }
  ]
}
```

Allowed axes are `correctness`, `readability`, `architecture`, `security`,
`performance`, `observability`, `resilience`, and `compatibility`. Description
prefix must match severity exactly: `Critical:`, `Nit:`, `Optional:`, `FYI:`,
or `none:`. Critical findings must use `fix` or `escalate`; security findings
must never use `accept`; positive observations use severity `none` with
disposition `accept`. Split distinct issues into separate findings. Include
precise file and line locations for code-level issues. If no defect exists,
include at least two `none` observations on different axes to prove review
coverage.
