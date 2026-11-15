# Implementation Findings: reject-vacuous-worker-results-in-the-package-executor

## Iteration 1 (PR #704 remediation)

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | bug | high | `result_validator` failed to import `package_acceptance` when loaded by file path in an installed consumer (test-infra-skills, coverage-ratchet) | Scripts put their own directory on `sys.path` |
| 2 | security | high | Acceptance checked `files_modified` only against the worker-echoed `scope` (PR review, codex P1) | `package_scope` check against `package_def["scope"]`; missing scope refused |
| 3 | edge-case | medium | A failing step without `name` raised `KeyError` (PR review, codex P2) | `s.get("name", "?")`; acceptance also refuses on `KeyError` |
| 4 | workflow | medium | wp-contract / wp-integration omitted `apis` / `documentation` context_impact surfaces (context-drift-gate) | Declared |
| 5 | bug | high | Stale accepted verdict could pass a replaced result (PR review, codex P1) | Already fixed in 0e6fa4ca (`result_digest` binding); no change |

## Vendor review remediation

Vendors: antigravity, codex, grok (ok); pi failed (provider HTTP 403). Consensus: 8 findings, 1 confirmed, 0 blocking.

| # | Type | Criticality | Source | Description | Disposition |
|---|------|-------------|--------|-------------|-------------|
| 6 | security | high | grok (single vendor, orchestrator-adjudicated valid, reproduced) | `src/api/../../SECRET.md` string-matched `src/api/**` | Fixed: unnormalized paths refused in `validate_scope_compliance` |
| 7 | edge-case | medium | grok | No test pinned traversal | Fixed: tests added |
| 8 | security | low | claude_code + antigravity (confirmed) | `files_modified` is self-reported, not compared with the commit diff | Accepted: explicit proposal non-goal |
| 9 | resilience | low | antigravity | Truthy non-dict `git` raises AttributeError in the standalone CLI | Accepted: refused at the acceptance decision point |
