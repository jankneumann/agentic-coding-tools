# Plan Findings: bind-merge-verdicts-to-head-sha-and-patch-id

## Iteration 1 (2026-11-15, PR #701 remediation)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | feasibility | high | Execution reads live state through `validate_pr` (`get_live_status=validate_pr`), which builds its own dict; adding `headRefOid` to `get_pr_status` alone never reaches the predicate or merge pin, so every verdict would classify `stale`. | D6 and tasks 3.2/3.4 now require `validate_pr` to return `head_sha`, with a test. |
| 2 | feasibility | high | wp-vendor-review changes `review_dispatcher.py`, but wp-docs could not write the `parallel-infrastructure` runtime mirrors that `install.sh` regenerates. | wp-docs `write_allow` and task 6.5 cover `.claude/` and `.agents/skills/parallel-infrastructure/**`. |
| 3 | consistency | high | context-drift-gate failed on #703: wp-schema implies `apis` (merge-plan.schema.json), wp-docs implies `documentation`. | Surfaces declared; `validate_context_impact` VALID against #703's changed files. |
| 4 | clarity | medium | Head-mismatch detection left to unspecified stderr text, overlapping the merge-queue stderr routing. | D6 pins the markers and a structured `head_mismatch: True` response key; 5.2 asserts on the key. |
| 5 | completeness | medium | No task tests the `_review_evidence` extension (`binding`, `review_waiver`). | Added task 5.3a in `test_execute_plan_review_evidence.py`. |
| 6 | testability | medium | "Eligible vendor review fails closed" had no scenario ID; `cheap-path-dropped-on-comments` had no ID comment in tasks. | IDs added in spec and tasks 5.1/5.2. |
| 7 | completeness | medium | No scenario for a `{"skipped": true}` review lacking both a current binding and a waiver; design risk row omitted it and `changes_requested`. | Added scenario `skip-path-without-binding-or-waiver-blocks`; design risk row aligned. |
| 8 | testability | medium | Tasks 3.2 and 5.3 named no test file. | Files named. |
