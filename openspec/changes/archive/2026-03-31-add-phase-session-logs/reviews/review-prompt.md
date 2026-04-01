# Plan Review: add-phase-session-logs

Review the OpenSpec plan artifacts in `openspec/changes/add-phase-session-logs/`.

## Artifacts to Read

1. `proposal.md` — Problem statement, solution overview, scope, risks
2. `design.md` — Architecture, formats, integration points, concurrency model
3. `tasks.md` — Implementation task breakdown with dependencies
4. `specs/skill-workflow/spec.md` — Delta spec with 8 requirements (4 modified, 4 new)

## Review Focus

Evaluate the plan against:
- **Specification completeness**: All requirements use SHALL/MUST, are testable, have success + failure scenarios
- **Architecture alignment**: Design follows existing codebase patterns, no unnecessary coupling
- **Security**: Sanitization covers all secret patterns, no leaks possible in committed artifacts
- **Work package validity**: Task dependencies are correct, scopes don't overlap, parallelism is sound

## Output

Output ONLY valid JSON conforming to `openspec/schemas/review-findings.schema.json`. Structure:

```json
{
  "review_type": "plan",
  "target": "add-phase-session-logs",
  "reviewer_vendor": "<your-model-name>",
  "findings": [
    {
      "id": 1,
      "type": "spec_gap|contract_mismatch|architecture|security|performance|style|correctness",
      "criticality": "low|medium|high|critical",
      "description": "...",
      "resolution": "...",
      "disposition": "fix|regenerate|accept|escalate"
    }
  ]
}
```
