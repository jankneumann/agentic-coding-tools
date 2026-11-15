# Implementation Findings

## Iteration 1 (PR #702 remediation)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | workflow | high | `context-drift-gate` blocked: `wp-expedite` writes `skills/expedite/SKILL.md` and `docs/mental-models.md` but its `context_impact` declared only `semantic_code`, so the implied `documentation` surface was undeclared. | Declared `documentation` in `wp-expedite.context_impact.surfaces`; `validate_context_impact.py --base main` now VALID and `make context-drift-gate CONTEXT_GATE_EVENT=pull_request` reports fresh. |
| 2 | edge-case | medium | Review thread (codex, on d03f8946): drift suite compared only check names, so flipping `iterate` to pass or deleting the hard-gate-fail row stayed green. | Already fixed in dea4e861 by `test_table_rows_equal_failing_conditions`, which reconciles (check, condition) table rows with observed failing conditions. Re-verified by mutation: both named mutations now fail that test. No code change. |

## Vendor review (iteration 2 remediation)

Dispatched to antigravity, codex, grok, pi (claude_code excluded as primary). Succeeded: antigravity (gemini-3.8-flash-high), grok (grok-4.5). Timed out at 500s: codex, pi. Consensus quorum met (3/3 incl. claude_code); 1 confirmed, 5 unconfirmed, 0 disagreements, 0 blocking. Antigravity's one finding is a verbatim copy of the primary reviewer's file (`review-findings-impl.json` was present in the reviewed tree), so the "confirmed" count is not independent.

| # | Source | Criticality | Description | Resolution |
|---|--------|-------------|-------------|------------|
| V1 | grok | medium | An explicit `--validation-report` path that does not exist was treated as a present report: the override was ignored and the detail came from `pre_merge_gate`. | Fixed (adjudicated: reproduced by new failing tests). `_report_missing()` treats a non-existent explicit path as no report; the check fails naming that path, and the override applies. New spec scenario `expedite.explicit-missing-path-is-missing`. |
| V2 | grok | low | Override reason recorded unstripped. | Fixed: `_override_reason` returns the stripped reason. |
| V3 | grok | low | SKILL.md hard-gate row says "pass `--force`" without naming the consumer. | Fixed: "at merge time (`expedite.py` itself has no `--force`)". |
| V4 | grok | low | No test pins PermissionError as an unreadable report. | Deferred: same `except Exception` branch as the covered non-UTF-8 and directory cases; root-run CI makes a chmod test unreliable. |
| V5 | claude_code / antigravity | low | Bare `except Exception` around `pre_merge_gate`. | Accepted: fails closed and names the exception class. |
