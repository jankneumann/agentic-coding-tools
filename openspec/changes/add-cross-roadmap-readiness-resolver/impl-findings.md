# Implementation Findings: Add Cross-Roadmap Readiness Resolver

## Round 1

Antigravity independently returned eight schema-valid `severity=none` findings covering the authority boundary, checkpoint semantics, typed dependencies, determinism, compatibility, security, and test evidence. The primary Codex review identified two additional deterministic gaps.

| ID | Criticality | Finding | Disposition |
|---|---:|---|---|
| C1 | medium | Duplicate item ids inside one roadmap are not rejected by JSON Schema and make identity ambiguous. | Fix with semantic validation and RED regression. |
| C2 | low | Helper exit-code logic is tested but the actual CLI boundary is not. | Fix with stdout/status regression. |
| A1-A8 | low | Independent review found the implementation aligned with the approved design. | Accepted; no change required. |

No roadmap re-decomposition or scope expansion is required.
## Remediation

Both primary findings are fixed. The duplicate-item regression failed with two ready entries before the semantic guard and passes after a linear-time duplicate check emits `roadmap_invalid`. The direct `main()` regression proves hard-invalid input emits parseable newline-terminated JSON and exits 2. The focused matrix now passes 465 tests.
