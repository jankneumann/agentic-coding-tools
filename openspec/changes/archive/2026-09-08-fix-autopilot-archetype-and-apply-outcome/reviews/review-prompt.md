# Plan Review — fix-autopilot-archetype-and-apply-outcome

You are an independent reviewer of the OpenSpec change at `openspec/changes/fix-autopilot-archetype-and-apply-outcome/`. Read these artifacts as read-only input:

- `openspec/changes/fix-autopilot-archetype-and-apply-outcome/proposal.md`
- `openspec/changes/fix-autopilot-archetype-and-apply-outcome/design.md`
- `openspec/changes/fix-autopilot-archetype-and-apply-outcome/tasks.md`
- `openspec/changes/fix-autopilot-archetype-and-apply-outcome/specs/skill-workflow/spec.md`

## Background context

The change addresses two contract violations surfaced during a recent autopilot run for `extract-gen-eval-package`:

- **V1**: VALIDATE phase maps to read-only `analyst` archetype; sub-agent stalled at 600s watchdog due to prompt contradiction (analyst says "without making changes", VALIDATE task writes evidence).
- **V2**: IMPLEMENT sub-agent prematurely transitioned `loop-state.current_phase` from IMPLEMENT directly to CLEANUP (a non-autopilot-state-machine state, skipping 4 phases). Cause is either (a) `apply-outcome` writes `current_phase` in violation of SKILL.md, or (b) the sub-agent ran extra bookkeeping beyond its mandate.

## What you should evaluate

Apply the **five-axis / five-severity** review schema (see `openspec/schemas/review-findings.schema.json`). Look for:

1. **Correctness gaps**: Does the proposal correctly identify the failure modes? Are there missing pathways (e.g., a third cause of V2 that neither Layer A nor Layer B addresses)?
2. **Design choices that could go wrong**: D1's "fix both layers" approach; D2's choice of new `validator` archetype vs. reusing `runner`; D4's `--force` semantics.
3. **Spec scenarios**: Are they testable? Are they brittle to rephrasing (e.g., substring-based read-only-marker checks)?
4. **Architecture alternatives**: Is there a structural alternative (file permissions, hooks) to the prompt-based prohibition that's not even named in "Out of Scope"?
5. **Resilience**: What happens when the fixed `apply-outcome` itself fails? Is the orchestrator's error handling specified?
6. **Backward compatibility**: D7's matrix — anything missing?
7. **Test plan adequacy**: Do Tasks 5-7 actually exercise the fixes?

## Output format

Emit a single JSON object conforming to `openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "fix-autopilot-archetype-and-apply-outcome",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness | readability | architecture | security | performance",
      "severity": "critical | nit | optional | fyi | none",
      "type": "spec_gap | contract_mismatch | architecture | security | performance | style | correctness | observability | compatibility | resilience | behavioral_failure",
      "criticality": "low | medium | high | critical",
      "description": "<prefix matches severity: Critical: / Nit: / Optional: / FYI: / no prefix for none>: <issue>",
      "resolution": "<concrete fix or 'no action required'>",
      "disposition": "fix | regenerate | accept | escalate",
      "file_path": "<optional, openspec/changes/.../...md>",
      "line_range": {"start": <int>, "end": <int>}
    }
  ]
}
```

## Rules

- Emit only valid JSON. No prose around the JSON.
- Every finding MUST have both `axis` and `severity` (schema-required).
- `description` MUST start with the prefix matching `severity` (`Critical:`, `Nit:`, `Optional:`, `FYI:`, or no prefix for `none`).
- Pick exactly one `axis` per finding. Split multi-axis observations into separate findings.
- Be honest: if you find nothing wrong, emit `severity: none` positive observations naming what the change got right. A zero-finding review signals the reviewer didn't actually engage.
- Don't hallucinate file paths or line numbers. The 4 artifact paths above are the only valid `file_path` values.
- Calibrate severity carefully: `critical` blocks merge; `nit` should-fix; `optional` consider; `fyi` informational; `none` positive.

## Submit

Write your JSON to stdout. The dispatcher will parse and route it to consensus synthesis alongside other vendors' findings.
