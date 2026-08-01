# Independent implementation review: harden-review-consensus-and-recovery

Act as a read-only code reviewer. Review the implementation on the current branch against base commit `247bc201cbfab7ee4a1441f0d293ad16031247a5` and the OpenSpec change `harden-review-consensus-and-recovery`.

Inspect the complete feature diff with:

```bash
git diff 247bc201cbfab7ee4a1441f0d293ad16031247a5...HEAD
```

Read these requirements and contracts:

- `openspec/changes/harden-review-consensus-and-recovery/proposal.md`
- `openspec/changes/harden-review-consensus-and-recovery/design.md`
- `openspec/changes/harden-review-consensus-and-recovery/specs/skill-workflow/spec.md`
- `openspec/changes/harden-review-consensus-and-recovery/specs/agent-archetypes/spec.md`
- `openspec/changes/harden-review-consensus-and-recovery/tasks.md`
- `openspec/changes/harden-review-consensus-and-recovery/work-packages.yaml`
- `openspec/changes/harden-review-consensus-and-recovery/contracts/consensus-policy.schema.json`
- `openspec/changes/harden-review-consensus-and-recovery/contracts/review-attempt.schema.json`

Focus on correctness, security, performance, architecture, readability, compatibility, and exact contract/spec compliance. Pay special attention to fail-closed behavior, deterministic consensus grouping, adjudication semantics, attempt-chain bounds, monotonic deadline handling, vendor replacement/deduplication, quorum eligibility, routing precedence, thinking translation, provenance, redaction, checkpoint durability, and legacy caller compatibility. Do not modify any files.

Return only one JSON object. It must have this shape:

```json
{
  "review_type": "implementation",
  "target": "whole-branch",
  "reviewer_vendor": "your vendor/model identifier",
  "findings": [
    {
      "id": 1,
      "axis": "correctness",
      "severity": "critical",
      "type": "correctness",
      "criticality": "critical",
      "description": "Critical: path/to/file.py:42 concise issue and impact",
      "resolution": "Specific required fix",
      "disposition": "fix",
      "package_id": "whole-branch",
      "file_path": "path/to/file.py",
      "line_range": {"start": 42, "end": 44}
    }
  ]
}
```

Allowed `axis`: `correctness`, `readability`, `architecture`, `security`, `performance`.

Allowed `severity`: `critical`, `nit`, `optional`, `fyi`, `none`. The description must start with the matching marker `Critical:`, `Nit:`, `Optional:`, `FYI:`, or `none:`. Use `critical` only for merge-blocking defects. Critical findings must use disposition `fix` or `escalate`. Security findings must not use `accept`. Positive observations may use severity `none` and disposition `accept`.

Allowed `type`: `spec_gap`, `contract_mismatch`, `architecture`, `security`, `performance`, `style`, `correctness`, `observability`, `compatibility`, `resilience`.

Allowed `disposition`: `fix`, `regenerate`, `accept`, `escalate`.

Every code-level finding must include an accurate repo-relative `file_path` and `line_range`. Split distinct issues into separate findings. If there are no defects, include at least one `none` positive observation demonstrating that the diff was inspected.
