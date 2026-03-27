# Plan Review: automated-dev-loop

You are reviewing an OpenSpec proposal for the `automated-dev-loop` feature. Read all artifacts below and produce structured findings.

## Artifacts to Review

Read these files in the current working directory:
- `openspec/changes/automated-dev-loop/proposal.md` — What and why
- `openspec/changes/automated-dev-loop/design.md` — Architecture and component design
- `openspec/changes/automated-dev-loop/specs/skill-workflow/spec.md` — Requirements with scenarios
- `openspec/changes/automated-dev-loop/tasks.md` — Task decomposition
- `openspec/changes/automated-dev-loop/work-packages.yaml` — Work package DAG

Also review these existing dependencies to verify interface assumptions:
- `skills/parallel-implement-feature/scripts/review_dispatcher.py` — Review dispatch interface
- `skills/parallel-implement-feature/scripts/consensus_synthesizer.py` — Consensus synthesis interface
- `openspec/schemas/review-findings.schema.json` — Finding schema
- `openspec/schemas/consensus-report.schema.json` — Consensus schema

## Review Dimensions

1. **Specification completeness** — Are requirements testable? Any gaps?
2. **Contract consistency** — Do schemas and interfaces match?
3. **Architecture alignment** — Does the design follow existing codebase patterns?
4. **Security** — Any vulnerabilities in the automated dispatch model?
5. **Work package validity** — DAG correctness, scope overlaps, dependency completeness?
6. **Correctness** — Logic errors in convergence algorithm, state machine, strategy selector?

## Output Format

Output ONLY valid JSON conforming to the review-findings schema. No markdown, no explanation — just the JSON object:

```json
{
  "review_type": "plan",
  "target": "automated-dev-loop",
  "reviewer_vendor": "<your-model-name>",
  "findings": [
    {
      "id": 1,
      "type": "spec_gap|contract_mismatch|architecture|security|performance|style|correctness",
      "criticality": "low|medium|high|critical",
      "description": "What the issue is",
      "resolution": "How to fix it",
      "disposition": "fix|regenerate|accept|escalate",
      "file_path": "path/to/relevant/file (optional)",
      "line_range": {"start": 1, "end": 10}
    }
  ]
}
```

Be thorough. Focus on medium+ severity issues. Include file_path when applicable for cross-vendor matching.
