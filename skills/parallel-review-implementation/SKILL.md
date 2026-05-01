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

Optional flags:
- `--adversarial` — Use adversarial review mode: challenges design decisions instead of standard review

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

## Five-Axis Finding Schema

Every finding produced by this skill MUST be classified into BOTH dimensions below. The JSON Schema at `openspec/schemas/review-findings.schema.json` enforces both fields as `required` — output that omits either is rejected by the validator in Step 7.

### Five Axes (the `axis` field)

Adopted from the `code-review-and-quality` reference skill. Pick exactly one per finding:

| Axis | What it covers in implementation review |
|---|---|
| `correctness` | Does the code do what the spec/contract demands? Bugs, off-by-one, broken edge cases, wrong return values. |
| `readability` | Will the next maintainer understand intent? Naming, comments, dead code, unclear control flow. |
| `architecture` | Does the change respect module boundaries? Coupling, layering, dependency direction, premature abstraction, scope creep. |
| `security` | Does the code introduce or fail to prevent risk? Injection, missing auth/authz, insecure defaults, leaked secrets, OWASP categories. |
| `performance` | Will it scale? N+1 queries, unbounded loops, missing pagination, sync calls in hot paths, memory blowups. |

The legacy `type` enum (`spec_gap`, `contract_mismatch`, etc. — see Step 6) is preserved for backward compatibility; `axis` is the new mandatory categorization that all reviewers — human or vendor — must agree on.

### Five Severity Prefixes (the `severity` field)

Every finding's `description` MUST begin with one of these markers. The `severity` enum value MUST match the prefix.

| Prefix | Severity value | Meaning |
|---|---|---|
| `Critical` | `critical` | Blocks merge. Must be fixed before integration. |
| `Nit` | `nit` | Should fix but does not block. Quality, naming, minor structure. |
| `Optional` | `optional` | Consider it. Author may accept or reject without further discussion. |
| `FYI` | `fyi` | Informational. Surfaces context the author may not have known; no action required. |
| `none` | `none` | Positive observation. Names what the implementation got right so good patterns survive review. |

Example finding (note prefix and matching `severity`):

```json
{
  "id": 1,
  "axis": "security",
  "severity": "critical",
  "type": "security",
  "criticality": "critical",
  "description": "Critical: handlers/users.py:42 builds the SQL query with f-string concatenation of `request.user_id` — SQL injection vector.",
  "resolution": "Use a parameterized query (`?` placeholder + bound value) via the existing `db.execute(query, params)` helper.",
  "disposition": "fix",
  "package_id": "wp-backend",
  "file_path": "handlers/users.py",
  "line_range": {"start": 42, "end": 44}
}
```

Reviewers MUST NOT collapse multiple severities onto one finding (split them). Reviewers MUST NOT use a severity that contradicts the `disposition` (e.g., `severity: critical` with `disposition: accept` is incoherent — escalate instead).

## Steps

### 0. Detect Review Mode

Before loading review context, determine the review mode:

```bash
if [ -f "openspec/changes/$CHANGE_ID/work-packages.yaml" ]; then
  # Verify the file is valid YAML
  python3 -c "import yaml; yaml.safe_load(open('openspec/changes/$CHANGE_ID/work-packages.yaml'))" 2>/dev/null
  if [ $? -eq 0 ]; then
    REVIEW_MODE="per-package"
  else
    REVIEW_MODE="whole-branch"
    echo "WARNING: work-packages.yaml exists but cannot be parsed. Falling back to whole-branch review."
  fi
else
  REVIEW_MODE="whole-branch"
fi
```

**Whole-branch mode**: When `work-packages.yaml` is missing or malformed, treat the entire branch diff as a single review unit. Use `package_id: "whole-branch"` in findings output. Skip Steps 2 (Scope Verification) and conditionally skip Step 3 (Contract Compliance) based on contract availability.

**Per-package mode**: When `work-packages.yaml` exists and is valid, use existing per-package review logic (Steps 1-6 unchanged).

If `REVIEW_MODE` is "whole-branch", skip to Step 1-WB below. Otherwise, continue with Step 1 as normal.

### 1-WB. Load Whole-Branch Review Context

When in whole-branch mode:

1. Compute the full branch diff: `git diff <base>...<head>`
2. Check for contracts:
   - If `contracts/` exists AND contains files other than `README.md`: load contract artifacts for compliance review
   - If `contracts/` is missing or contains only `README.md`: skip contract compliance (Step 3)
3. Read traced requirements from `specs/**/spec.md`
4. Set `PACKAGE_ID="whole-branch"` for all findings output

After loading context, skip to Step 3 (if contracts exist) or Step 4 (if no contracts).

### 1. Load Review Context

Parse the package-id argument and load:

1. Read `work-packages.yaml` and extract the target package definition
2. Read relevant contract artifacts (OpenAPI, DB schema, event schemas)
3. Read the git diff for this package's worktree
4. Read the work-queue result JSON (if available)
5. Read traced requirements from `specs/**/spec.md`

### 2. Scope Verification

**Skip this step in whole-branch mode** (no package scopes to verify).

Before reviewing code quality, verify scope compliance:

- [ ] All modified files are within the package's `write_allow` globs
- [ ] No modified files match `deny` globs
- [ ] Lock keys match the package's declared locks

If scope violations are found, emit a `correctness` finding with `critical` criticality.

### 3. Contract Compliance Review

**In whole-branch mode**: Skip this step if `contracts/` is missing or contains only `README.md`. If machine-readable contract artifacts exist, perform compliance review against the full branch diff instead of per-package diff.

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
- [ ] Observability: structured logging for key operations, error context in exception handlers, health/readiness endpoints for new services
- [ ] Compatibility: no unannounced breaking changes to existing APIs, migration scripts are reversible, deprecation notices for changed interfaces
- [ ] Resilience: timeout configuration for external calls, retry with backoff where appropriate, idempotent operations for retryable paths
- [ ] Code follows existing project conventions

### 5. Verification Result Cross-Check

If work-queue result is available:

- [ ] `verification.passed` is consistent with step results
- [ ] Test count is reasonable for the scope of changes
- [ ] No escalations are unaddressed

### 5.5. Adversarial Mode (Optional)

If `--adversarial` flag was passed, the review prompt should be wrapped with adversarial framing:

```python
from adversarial_prompt import wrap_adversarial
prompt = wrap_adversarial(prompt)  # Prepends contrarian persona instructions
```

This changes the review persona to challenge design decisions rather than just checking correctness. The dispatch mode remains `review` (unchanged) and findings use the standard schema.

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
- `observability` — Missing logging, metrics, or health endpoints
- `compatibility` — Breaking change to existing API or missing migration rollback
- `resilience` — Missing retry, timeout, or idempotency handling

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

**Integration Gate Logic** (orchestrator-side, consensus-aware):
- When consensus exists: confirmed fix → BLOCKED_FIX, disagreement → BLOCKED_ESCALATE, unconfirmed → warnings (pass)
- When no consensus: fall back to single-vendor finding dispositions
- Any `fix` finding → return to package agent for remediation
- Any `escalate` finding → trigger escalation protocol

## Design for Vendor Diversity

Like `parallel-review-plan`, this skill is self-contained:
- No coordinator dependencies required for execution
- All input is file-based (read-only)
- Output is a single JSON file with a well-defined schema
- No side effects
- Can be dispatched to any LLM vendor for independent review

When this skill is dispatched *to* another vendor by the orchestrator, only the review steps run (produce findings). Multi-vendor dispatch is handled by the orchestrating agent in Phase C3 of `/parallel-implement-feature`.

**Agent discovery resolution chain**: The dispatcher resolves agents via the coordination MCP server configured in `~/.claude.json` → `mcpServers.coordination`. It extracts the `agent-coordinator/` directory from the MCP server args and runs `get_dispatch_configs.py` to load `agents.yaml`. If the coordinator is not configured, pass `--agents-yaml <path>` explicitly as fallback. Use `--list-agents` to verify available agents.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "The diff is small — I'll skip the axis classification" | The schema rejects findings without `axis`/`severity` regardless of diff size. Cross-vendor consensus matches findings by axis + file_path + line_range; missing axis means your review is invisible to the integration gate. |
| "This is a `correctness` issue but it also has `security` implications — I'll merge them" | Split into two findings. The integration gate routes `security` findings differently (mandatory `fix`, never `accept`). Burying security under correctness lets the gate under-react. |
| "The verification result already says PASS — I don't need to look at the code" | The verification cross-check (Step 5) is necessary but not sufficient. PASS only means the package's own tests passed; cross-package interactions, security, and architectural fit are not covered. |
| "I'll mark everything `Nit` to be polite" | Politeness is not the goal; truth is. A `Critical` finding marked `Nit` causes the integration gate to merge a broken change. Use `none` for positive observations instead of downgrading real issues. |

## Red Flags

- A `review-findings.json` for a non-empty diff that contains zero findings AND no `severity: none` positive observations — the reviewer almost certainly did not actually read the diff.
- `severity: critical` paired with `disposition: accept` — these contradict each other; the orchestrator's integration gate cannot resolve this safely.
- A finding with `axis: security` and `disposition: accept` — security findings must be `fix` or `escalate`, never silently accepted.
- Description prose lacks the matching severity prefix (`Critical:` / `Nit:` / `Optional:` / `FYI:`). The prefix is the human-readable signal; if it disagrees with the enum, the reviewer wrote JSON without re-reading the prose.
- Findings without `file_path`/`line_range` for code-level issues (correctness, security, performance) — these fields are what enables cross-vendor consensus matching; omitting them isolates the finding.
- Scope-violation findings missing — modified files outside the package's `write_allow` should always produce a `correctness` + `severity: critical` finding (see Step 2).

## Verification

1. Run the JSON Schema validator from Step 7 and confirm `Valid` — this proves `axis` and `severity` are present on every finding.
2. Spot-check 3 findings: confirm the `description` text begins with the prefix matching the `severity` enum value (e.g., `severity: critical` ↔ description starts with `Critical:`).
3. Confirm `disposition` is coherent with `severity` AND `axis`: `security` findings never `accept`; `critical` findings always `fix` or `escalate`; `none` findings always `accept`.
4. Confirm at least two different `axis` values appear across the findings array (a single-axis review missed the other four dimensions of the schema).
5. Confirm scope verification (Step 2) actually ran in per-package mode — if any modified file was outside `write_allow`, it must appear as a `severity: critical` finding.
6. Confirm `reviewer_vendor` and `package_id` (or `target: "whole-branch"` in whole-branch mode) are populated — anonymous or untargeted findings cannot participate in consensus.
