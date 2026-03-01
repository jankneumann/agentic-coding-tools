---
name: parallel-review-implementation
description: Per-package implementation review producing structured findings per review-findings.schema.json
category: Git Workflow
tags: [openspec, review, implementation, parallel, quality]
triggers:
  - "parallel review implementation"
  - "review parallel implementation"
requires:
  coordinator:
    required: []
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_AUDIT]
---

# Parallel Review Implementation

Receive a work package diff as read-only input and produce structured findings conforming to `review-findings.schema.json`. Designed for vendor-diverse dispatch — runs independently per package.

## Arguments

`$ARGUMENTS` - `<change-id> <package-id>` (e.g., "add-user-auth wp-backend")

## Prerequisites

- Work package implementation is complete
- Package worktree has committed changes
- Work-queue result JSON is available

## Input (Read-Only)

The reviewer receives per-package context:

- **Package definition** from `work-packages.yaml` (scope, locks, verification)
- **Contract artifacts** from `contracts/` relevant to this package
- **Git diff** of all files modified by this package (`git diff <base>...<head>`)
- **Work-queue result** JSON (verification results, files_modified, escalations)
- **Spec requirements** traced to this package via `tasks.md`

The reviewer MUST NOT modify any files.

## Steps

### 1. Load Review Context

Parse the package-id argument and load:

1. Read `work-packages.yaml` and extract the target package definition
2. Read relevant contract artifacts (OpenAPI, DB schema, event schemas)
3. Read the git diff for this package's worktree
4. Read the work-queue result JSON (if available)
5. Read traced requirements from `specs/**/spec.md`

### 2. Scope Verification

Before reviewing code quality, verify scope compliance:

- [ ] All modified files are within the package's `write_allow` globs
- [ ] No modified files match `deny` globs
- [ ] Lock keys match the package's declared locks

If scope violations are found, emit a `correctness` finding with `critical` criticality.

### 3. Contract Compliance Review

Check that the implementation matches declared contracts:

- [ ] API endpoints match OpenAPI path/method/response schemas
- [ ] Database queries use only declared tables and columns
- [ ] Event payloads match event contract schemas
- [ ] Error responses follow the specified format (e.g., RFC 7807)

#### For Backend Packages
- [ ] All OpenAPI-declared endpoints are implemented
- [ ] Request validation matches schema constraints
- [ ] Response serialization matches declared types

#### For Frontend Packages
- [ ] API calls use generated TypeScript types
- [ ] Error handling covers all declared error responses
- [ ] Events are consumed with correct schema

### 4. Code Quality Review

Standard code review criteria:

- [ ] Tests cover the new functionality adequately
- [ ] No hardcoded values that should be configuration
- [ ] Error handling is complete (no bare except/catch)
- [ ] No security vulnerabilities (SQL injection, XSS, command injection)
- [ ] Performance considerations (N+1 queries, unbounded loops, missing pagination)
- [ ] Code follows existing project conventions

### 5. Verification Result Cross-Check

If work-queue result is available:

- [ ] `verification.passed` is consistent with step results
- [ ] Test count is reasonable for the scope of changes
- [ ] No escalations are unaddressed

### 6. Produce Findings

Generate findings as JSON conforming to `review-findings.schema.json`:

```json
{
  "review_type": "implementation",
  "target": "<package-id>",
  "reviewer_vendor": "<model-name>",
  "findings": [
    {
      "id": 1,
      "type": "contract_mismatch",
      "criticality": "high",
      "description": "POST /v1/users returns 200 but OpenAPI spec declares 201",
      "resolution": "Change response status code to 201 Created",
      "disposition": "fix",
      "package_id": "wp-backend"
    }
  ]
}
```

#### Finding Types
- `spec_gap` — Implementation misses a spec requirement
- `contract_mismatch` — Code doesn't match contract (OpenAPI, DB schema, events)
- `architecture` — Structural concern or pattern violation
- `security` — Security vulnerability
- `performance` — Performance concern
- `style` — Code style or convention issue
- `correctness` — Bug or logical error

#### Dispositions
- `fix` — Must fix before integration merge
- `regenerate` — Contract needs updating (triggers escalation)
- `accept` — Minor issue, acceptable as-is
- `escalate` — Requires orchestrator decision (scope violation, contract revision)

### 7. Validate Output

```bash
python3 -c "
import json, jsonschema
schema = json.load(open('openspec/schemas/review-findings.schema.json'))
findings = json.load(open('<findings-output-path>'))
jsonschema.validate(findings, schema)
print('Valid')
"
```

### 8. Submit Findings

Write findings to `artifacts/<package-id>/review-findings.json`.

If any finding has `disposition: "escalate"` or `disposition: "regenerate"`, the orchestrator will handle escalation (pause-lock, contract revision bump, etc.).

## Output

- `artifacts/<package-id>/review-findings.json` conforming to `review-findings.schema.json`

## Orchestrator Integration

The orchestrator dispatches this skill once per completed work package:

1. Package completes → work-queue result submitted
2. Orchestrator validates result (schema, scope, verification)
3. Orchestrator dispatches review skill with package context
4. Review findings feed into integration gate decision

**Integration Gate Logic** (orchestrator-side):
- All packages reviewed with no `fix` or `escalate` findings → proceed to integration
- Any `fix` finding → return to package agent for remediation
- Any `escalate` finding → trigger escalation protocol

## Design for Vendor Diversity

Like `parallel-review-plan`, this skill is self-contained:
- No coordinator dependencies required for execution
- All input is file-based (read-only)
- Output is a single JSON file with a well-defined schema
- No side effects
- Can be dispatched to any LLM vendor for independent review
