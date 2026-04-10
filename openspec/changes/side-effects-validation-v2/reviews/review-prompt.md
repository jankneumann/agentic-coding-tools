# Plan Review: side-effects-validation-v2

You are reviewing an OpenSpec plan for extending the gen-eval framework with side-effects validation, semantic evaluation, and extended assertions. This is a re-plan of PR #72 which was abandoned due to merge conflicts.

## Your Task

1. Read all plan artifacts listed below
2. Evaluate the plan against the review checklist
3. Output ONLY valid JSON conforming to the review-findings schema (no other text)

## Plan Artifacts to Read

Read these files in the repository:

- `openspec/changes/side-effects-validation-v2/proposal.md` — What and why
- `openspec/changes/side-effects-validation-v2/design.md` — How (design decisions D1-D8)
- `openspec/changes/side-effects-validation-v2/tasks.md` — Implementation plan (25 tasks across 3 phases)
- `openspec/changes/side-effects-validation-v2/specs/gen-eval-framework/spec.md` — Delta spec with ADDED and MODIFIED requirements
- `openspec/changes/side-effects-validation-v2/contracts/README.md` — Contract applicability analysis
- `openspec/changes/side-effects-validation-v2/work-packages.yaml` — 3 sequential work packages

Also read the current codebase to validate assumptions:
- `agent-coordinator/evaluation/gen_eval/models.py` — Current model definitions
- `agent-coordinator/evaluation/gen_eval/evaluator.py` — Current evaluator (will be extended)
- `agent-coordinator/evaluation/gen_eval/manifest.py` — Current manifest module
- `agent-coordinator/evaluation/gen_eval/__init__.py` — Package exports

## Review Checklist

Evaluate against these dimensions:
- **Specification Completeness**: SHALL/MUST language, testable requirements, no ambiguity
- **Contract Consistency**: Schemas match requirements
- **Architecture Alignment**: Follows existing patterns, no unnecessary deps
- **Security Review**: Input validation, no injection risks
- **Performance Review**: No unbounded operations, pagination/limits where needed
- **Compatibility Review**: Breaking changes identified, migration paths exist
- **Resilience Review**: Retry/timeout/fallback for external dependencies
- **Work Package Validity**: DAG correctness, scope non-overlap for parallel packages

## Output Format

Output ONLY a JSON object conforming to this schema:

```json
{
  "review_type": "plan",
  "target": "side-effects-validation-v2",
  "reviewer_vendor": "<your-model-name>",
  "findings": [
    {
      "id": 1,
      "type": "<spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience>",
      "criticality": "<low|medium|high|critical>",
      "description": "Clear description of the finding",
      "resolution": "Specific actionable resolution",
      "disposition": "<fix|regenerate|accept|escalate>"
    }
  ]
}
```

Finding types: spec_gap, contract_mismatch, architecture, security, performance, style, correctness, observability, compatibility, resilience.

Be thorough but precise. Focus on actionable findings that would improve the plan.
