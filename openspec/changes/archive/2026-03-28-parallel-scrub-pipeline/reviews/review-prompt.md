# Plan Review: parallel-scrub-pipeline

You are reviewing the plan artifacts for the `parallel-scrub-pipeline` OpenSpec change. Your job is to produce a JSON file with structured findings.

## Instructions

1. Read ALL of the following plan artifacts (they are in the repository at the paths shown):
   - `openspec/changes/parallel-scrub-pipeline/proposal.md`
   - `openspec/changes/parallel-scrub-pipeline/design.md`
   - `openspec/changes/parallel-scrub-pipeline/tasks.md`
   - `openspec/changes/parallel-scrub-pipeline/specs/skill-workflow/spec.md`
   - `openspec/changes/parallel-scrub-pipeline/contracts/internal/parallel-runner-api.yaml`
   - `openspec/changes/parallel-scrub-pipeline/work-packages.yaml`

2. Also read the EXISTING codebase files the plan modifies:
   - `skills/bug-scrub/scripts/main.py` — current orchestrator
   - `skills/fix-scrub/scripts/main.py` — current orchestrator
   - `skills/bug-scrub/scripts/collect_pytest.py` — example collector (check picklability)
   - `skills/fix-scrub/scripts/generate_prompts.py` — current prompt generator
   - `skills/parallel-implement-feature/scripts/review_dispatcher.py` — actual MVRO dispatch code

3. Evaluate the plan against these dimensions:
   - **Specification completeness**: All requirements testable? SHALL/MUST language?
   - **Contract consistency**: Do contracts match specs and existing code?
   - **Architecture alignment**: Does design follow existing patterns? Any hidden assumptions?
   - **Work package validity**: DAG correct? Scopes non-overlapping? Lock keys valid?
   - **Correctness**: Any logical errors? Race conditions? Pickling issues?

4. Output ONLY a valid JSON object conforming to this schema:

```json
{
  "review_type": "plan",
  "target": "parallel-scrub-pipeline",
  "reviewer_vendor": "<your-model-name>",
  "findings": [
    {
      "id": 1,
      "type": "<spec_gap|contract_mismatch|architecture|security|performance|style|correctness>",
      "criticality": "<low|medium|high|critical>",
      "description": "Clear description of the issue",
      "resolution": "Specific recommended fix",
      "disposition": "<fix|regenerate|accept|escalate>"
    }
  ]
}
```

5. Be thorough but precise. Focus on issues that would cause implementation failures, not style preferences. Pay special attention to:
   - Whether ProcessPoolExecutor can actually pickle the collector functions given how they're imported (sys.path.insert)
   - Whether the MVRO infrastructure paths referenced in the proposal actually exist
   - Whether work package scopes have conflicts
   - Whether contracts match the existing code interfaces
