# Plan Review — extract-gen-eval-package

You are reviewing an OpenSpec change proposal. The change extracts the `gen-eval` framework (~6.5 KLOC, 23 Python files) out of `agent-coordinator/evaluation/gen_eval/` into a new top-level `packages/gen-eval/` directory as a uv-installable package, migrates the coordinator to consume it as a path dependency, and updates all skills that invoke it.

A first iteration of self-review (`plan-findings.md`) already addressed 12 findings F1-F12 in commit `4dc310e`. **Review the CURRENT state**, not the pre-iterate state. The most important changes from that iteration:

- D3 surgical extraction (only `GenEvalMetrics` moves into the package; the other 10 classes in `evaluation/metrics.py` stay in agent-coordinator)
- D8 chose Option B (wheel + COPY) for Docker, keeping Railway service root unchanged
- D9 added `skills/playwright-validator/scripts/cli.py` and `findings.py` and `skills/gen-eval-scenario/SKILL.md` to the update list
- Task 3.1 path corrected to `agent-coordinator/tests/test_evaluation/test_gen_eval/`
- Task 2.4.1 added a surface test for `gen_eval.metrics`

## Artifacts to read (all paths relative to repo root)

- `openspec/changes/extract-gen-eval-package/proposal.md`
- `openspec/changes/extract-gen-eval-package/design.md`
- `openspec/changes/extract-gen-eval-package/tasks.md`
- `openspec/changes/extract-gen-eval-package/specs/gen-eval-framework/spec.md`
- `openspec/changes/extract-gen-eval-package/contracts/README.md`
- `openspec/changes/extract-gen-eval-package/work-packages.yaml`
- `openspec/changes/extract-gen-eval-package/plan-findings.md` (the previous-iteration triage record)

## Output

Emit STRICTLY a single JSON object conforming to `openspec/schemas/review-findings.schema.json`, with this exact envelope:

```json
{
  "review_type": "plan",
  "target": "extract-gen-eval-package",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness|readability|architecture|security|performance",
      "severity": "critical|nit|optional|fyi|none",
      "type": "spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure",
      "criticality": "low|medium|high|critical",
      "description": "<prefix-matching-severity>: <one or two sentences>",
      "resolution": "<concrete fix>",
      "disposition": "fix|regenerate|accept|escalate",
      "file_path": "<optional path>",
      "line_range": {"start": <int>, "end": <int>}
    }
  ]
}
```

DO NOT emit a bare array. The dispatcher will discard unparsable output.

## What to look for

Evaluate the plan against:

1. **Specification completeness** — Are SHALL clauses testable? Any ambiguous prose?
2. **Contract consistency** — The `contracts/README.md` says "no contracts apply" because this is a packaging change. Is that right?
3. **Architecture alignment** — Does the `packages/gen-eval/` convention actually fit? Does D3 surgical extraction make sense given the consumers it leaves alone?
4. **Security** — Any new attack surface from the path dependency? Wheel install from outside Docker context?
5. **Performance** — Lazy-import pattern preserved? Build time implications?
6. **Compatibility** — Breaking change strategy (the `evaluation.gen_eval` import path is removed atomically, no shim). Is that justified?
7. **Resilience** — Editable-install Docker semantics (D5/D8). Does the local vs Docker split actually work?
8. **Work package validity** — DAG cycles? Scope overlap between the 4 parallel post-2.C packages? Lock keys?
9. **Severity gradient** — Are there any genuinely critical/blocking findings the previous iteration missed?

## Severity prefix discipline

Every `description` MUST begin with the prefix matching its `severity` enum value: `Critical:`, `Nit:`, `Optional:`, `FYI:`, or nothing for `none`. Mismatches will be rejected as red flags.

If you find nothing material, emit at least one `severity: none` positive observation naming what the plan got right — proves the review actually ran. A genuinely-clean review with 0 findings looks like a timeout.

Be specific about file paths and line ranges. Don't hallucinate paths that aren't in the artifacts.
