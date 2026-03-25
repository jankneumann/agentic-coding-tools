---
name: parallel-validate-feature
description: Slim integration-only validation with evidence completeness checking for parallel workflow
category: Git Workflow
tags: [openspec, validation, parallel, evidence, integration]
triggers:
  - "parallel validate feature"
  - "parallel validate"
  - "validate parallel feature"
requires:
  coordinator:
    required: []
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_AUDIT]
---

# Parallel Validate Feature

Slim integration-only validation for the parallel workflow. Unlike `linear-validate-feature` which runs full deployment and behavioral testing, this skill focuses on evidence completeness — verifying that all work-queue results are valid and all contract compliance checks passed during implementation.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Implementation PR exists (from `/parallel-implement-feature`)
- All work packages completed with results
- Execution summary available

## Rationale

In the parallel workflow, validation is shifted left — each work package runs its own verification steps during Phase B, and the integration package (wp-integration) runs the full test suite during Phase C5. This skill provides a final evidence audit to confirm nothing was missed.

## Steps

### 1. Load Execution Context

Read the execution artifacts:

1. `openspec/changes/<change-id>/work-packages.yaml` — Package definitions
2. `artifacts/*/work-queue-result.json` — Per-package results (if present)
3. Execution summary from PR description or attached file

### 2. Evidence Completeness Check

For each work package, validate its result against `work-queue-result.schema.json`:

```bash
skills/.venv/bin/python "<skill-base-dir>/../validate-packages/scripts/validate_work_result.py" artifacts/<package-id>/result.json
```

#### Checks per package:

- [ ] Result JSON validates against `work-queue-result.schema.json`
- [ ] `contracts_revision` matches the current `work-packages.yaml` value
- [ ] `plan_revision` matches the current `work-packages.yaml` value
- [ ] `scope_check.passed` is `true` (no scope violations)
- [ ] `verification.passed` is `true`
- [ ] All declared `outputs.result_keys` are present in verification evidence
- [ ] No unresolved escalations with `disposition: "fix"` or `disposition: "escalate"`

### 3. Contract Compliance Audit

Verify that contract compliance evidence exists:

- [ ] Each implementation package's result includes scope compliance check
- [ ] Integration package result includes full test suite results
- [ ] If OpenAPI contracts exist, at least one package ran schema validation

### 4. Cross-Package Consistency

Check for consistency across packages:

- [ ] No two packages report modifications to the same file
- [ ] All packages used the same `contracts_revision`
- [ ] All packages used the same `plan_revision`

### 4.5. Populate Change Context Evidence (Phase 3)

Fill the Evidence column of `change-context.md` using work-queue results:

1. Read `openspec/changes/<change-id>/change-context.md` (generated during `/parallel-implement-feature`)
2. For each row in the Requirement Traceability Matrix:
   - Cross-reference with work-queue result verification evidence per package
   - If a package's `verification.passed` is `true` and its scope covers the requirement's files, set Evidence to `pass <SHA>`
   - If verification failed for the relevant package, set Evidence to `fail <SHA>`
   - If no package covers this requirement, set Evidence to `deferred (no package coverage)`
3. Update Coverage Summary with final counts
4. Verify Review Findings Summary section is complete (all `review-findings.json` files synthesized)

### 5. Produce Validation Report

Generate a structured validation report:

```json
{
  "change_id": "<change-id>",
  "validated_at": "<ISO-8601>",
  "packages_checked": 4,
  "evidence_complete": true,
  "checks": {
    "schema_validation": {"passed": true, "packages": 4},
    "revision_consistency": {"passed": true},
    "scope_compliance": {"passed": true},
    "verification_evidence": {"passed": true},
    "cross_package_consistency": {"passed": true},
    "change_context": {"requirements_verified": "8/8", "gaps": 0, "deferred": 0}
  },
  "issues": []
}
```

### 6. Present Results

If all checks pass:
- Report "Evidence validation complete — all packages verified"
- Recommend proceeding to `/parallel-cleanup-feature`

If any checks fail:
- List failures with package_id and specific issue
- Recommend remediation before cleanup

## Output

- Validation report (printed or written to `artifacts/validation-report.json`)
- Go/no-go recommendation for cleanup

## Design Notes

This skill is intentionally slim compared to `linear-validate-feature`:
- No local deployment (handled by wp-integration during implementation)
- No security scanning (handled per-package during Phase B)
- No behavioral testing (handled by verification steps during Phase B)
- Focus is on evidence audit — confirming the parallel execution protocol was followed correctly

## Next Step

After validation passes:
```
/parallel-cleanup-feature <change-id>
```
