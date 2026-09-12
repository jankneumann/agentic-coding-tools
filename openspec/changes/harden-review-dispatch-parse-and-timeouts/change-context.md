# Change Context: harden-review-dispatch-parse-and-timeouts

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md — Schema-Derived Review Prompt | Every review prompt is built from the canonical schema via a shared helper | --- | D1, D8 | skills/parallel-infrastructure/scripts/review_findings_schema.py, skills/autopilot/scripts/convergence_loop.py, skills/merge-pull-requests/scripts/vendor_review.py, skills/parallel-review-plan/SKILL.md, skills/parallel-review-implementation/SKILL.md | skills/tests/parallel-infrastructure/test_review_findings_schema.py | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md — Finding Coercion Before Validation | Alias table applied before fail-closed schema validation | contracts/finding-coercion.schema.json | D2 | skills/parallel-infrastructure/scripts/review_findings_schema.py, skills/parallel-infrastructure/scripts/finding-coercion.json | skills/tests/parallel-infrastructure/test_finding_coercion.py | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md — Schema Repair Retry | Exactly one constrained rewrite on parse/schema failure | --- | D3 | skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md — Raw Vendor Output Sidecar | Full stdout/stderr persisted for every dispatch | contracts/vendor-raw-output.schema.json | D6 | skills/parallel-infrastructure/scripts/checkpoint_findings.py, skills/parallel-infrastructure/scripts/review_dispatcher.py, skills/autopilot/scripts/convergence_loop.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |
| skill-workflow.5 | specs/skill-workflow/spec.md — Per-Vendor Dispatch Timeout Budget | Timeout table; converge() must pass a timeout into dispatch_and_wait | contracts/dispatch-timeout-budget.schema.json | D4 | skills/parallel-infrastructure/scripts/review_dispatcher.py, skills/autopilot/scripts/convergence_loop.py, skills/parallel-infrastructure/scripts/dispatch-timeout-budget.json | skills/autopilot/scripts/tests/test_convergence_loop.py | --- |
| skill-workflow.6 | specs/skill-workflow/spec.md — Judgment Ingest for Model Reviewers | CLI/SDK review findings ingested as judgment; payload cannot self-promote | --- | D5 | skills/parallel-infrastructure/scripts/review_findings_schema.py, skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |
| skill-workflow.7 | specs/skill-workflow/spec.md — Empty Or Blinded Review Is Not Success | Fast empty findings and timeouts are not successful reviews | contracts/dispatch-timeout-budget.schema.json | D7 | skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |
| skill-workflow.8 | specs/skill-workflow/spec.md — Vendor Timeout Enforcement | Per-vendor timeout; timed-out vendor is success=false | contracts/dispatch-timeout-budget.schema.json | D4 | skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |
| skill-workflow.9 | specs/skill-workflow/spec.md — Vendor Failure Resilience | Failed vendor skipped; does not vote empty success | --- | D7 | skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/tests/parallel-infrastructure/test_review_dispatch_replay.py | --- |
| skill-workflow.10 | specs/skill-workflow/spec.md — Review Dispatcher Protocol | Coerce, validate, optional repair before writing findings | --- | D2, D3 | skills/parallel-infrastructure/scripts/review_dispatcher.py | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | One prompt helper derived from the schema | `prompt_contract()` in review_findings_schema.py | Stops the 2026-08-24 prompt/schema drift |
| D2 | Coerce then validate | `coerce_findings_payload()` | Keep schema strict |
| D3 | Exactly one repair retry | CliVendorAdapter.dispatch repair pass | Bounded, not a full re-review |
| D4 | Per-vendor timeout through converge() | timeout budget table + dispatch_and_wait | 300s sat below Claude p50 |
| D5 | Model-review ingest is judgment | stamp after parse | evidence_class already existed |
| D6 | Raw stdout sidecar | checkpoint_findings.write_raw_output | 500-char excerpt lost the document |
| D7 | Fast-empty is not success | elapsed floor on findings:[] | pi --no-tools false consensus |
| D8 | Helper lives in review_findings_schema.py | single module | No new dependency direction |

## Coverage Summary

- **Requirements traced**: 10/10
- **Tests mapped**: 10 requirements have at least one test
- **Evidence collected**: 0/10 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
