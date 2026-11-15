# Implementation Findings

## Iteration 1 (PR #702 remediation)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | workflow | high | `context-drift-gate` blocked: `wp-expedite` writes `skills/expedite/SKILL.md` and `docs/mental-models.md` but its `context_impact` declared only `semantic_code`, so the implied `documentation` surface was undeclared. | Declared `documentation` in `wp-expedite.context_impact.surfaces`; `validate_context_impact.py --base main` now VALID and `make context-drift-gate CONTEXT_GATE_EVENT=pull_request` reports fresh. |
| 2 | edge-case | medium | Review thread (codex, on d03f8946): drift suite compared only check names, so flipping `iterate` to pass or deleting the hard-gate-fail row stayed green. | Already fixed in dea4e861 by `test_table_rows_equal_failing_conditions`, which reconciles (check, condition) table rows with observed failing conditions. Re-verified by mutation: both named mutations now fail that test. No code change. |
