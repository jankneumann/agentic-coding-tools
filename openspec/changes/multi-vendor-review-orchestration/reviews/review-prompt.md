You are reviewing a plan for the "multi-vendor-review-orchestration" feature. Your job is to review the plan artifacts and produce structured findings as JSON.

## Context

This feature adds the ability for a primary AI agent to dispatch plan and implementation reviews to different AI vendors (Codex, Gemini, Claude) and synthesize their findings into a consensus report.

## Artifacts to Review

Read these files in the current directory:

- `openspec/changes/multi-vendor-review-orchestration/proposal.md` — What and why
- `openspec/changes/multi-vendor-review-orchestration/design.md` — Architecture decisions and component design
- `openspec/changes/multi-vendor-review-orchestration/tasks.md` — Implementation tasks
- `openspec/changes/multi-vendor-review-orchestration/specs/skill-workflow/spec.md` — 23 requirements with BDD scenarios
- `openspec/changes/multi-vendor-review-orchestration/contracts/consensus-report.schema.json` — JSON Schema for consensus reports
- `openspec/changes/multi-vendor-review-orchestration/work-packages.yaml` — 6 work packages with DAG

## Review Checklist

Evaluate against these dimensions:
1. **Specification completeness** — Are requirements testable? Any gaps?
2. **Contract consistency** — Do schemas match requirements?
3. **Architecture alignment** — Does design follow good patterns? Missing error handling?
4. **Security** — Input validation, injection risks, permission model?
5. **Work package validity** — DAG correct? Scopes non-overlapping? Dependencies right?

## Output Format

Output ONLY valid JSON (no markdown, no explanation) conforming to this structure:

```json
{
  "review_type": "plan",
  "target": "multi-vendor-review-orchestration",
  "reviewer_vendor": "<your-model-name>",
  "findings": [
    {
      "id": 1,
      "type": "<spec_gap|contract_mismatch|architecture|security|performance|style|correctness>",
      "criticality": "<low|medium|high|critical>",
      "description": "Clear description of the issue",
      "resolution": "Suggested fix",
      "disposition": "<fix|regenerate|accept|escalate>"
    }
  ]
}
```

If you find no issues, return an empty findings array. Focus on substantive issues, not style.
