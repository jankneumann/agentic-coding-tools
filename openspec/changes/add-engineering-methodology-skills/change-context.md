# Change Context: add-engineering-methodology-skills

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | Engineering Methodology Skill Suite | New methodology skill is auto-discovered by install.sh | --- | D5 | --- | tests/_shared/test_conftest_helpers.py + per-skill test_skill_md.py × 10 | --- |
| skill-workflow.2 | Engineering Methodology Skill Suite | user_invocable assignment is honored by skill discovery | --- | D5 | --- | per-skill test_skill_md.py × 10 | --- |
| skill-workflow.3 | Engineering Methodology Skill Suite | Frontmatter schema preserved (name/description/category/tags/triggers/user_invocable/requires/related) | --- | D5 | --- | tests/_shared/test_conftest_helpers.py | --- |
| skill-workflow.4 | Common Tail Block Convention | User-invocable skill ships tail block (3 sections in order, ≥3 entries each) | --- | D2 | --- | per-skill test_skill_md.py × 18 (10 new + 8 ADAPT) | --- |
| skill-workflow.5 | Common Tail Block Convention | Infrastructure skill (user_invocable: false) is exempt | --- | D2 | --- | tests/_shared/test_conftest_helpers.py | --- |
| skill-workflow.6 | Common Tail Block Convention | Tail-block template is available at skills/references/skill-tail-template.md | --- | D2, D3 | --- | tests/install_sh/test_references_rsync.py | --- |
| skill-workflow.7 | Shared References Library | references/ installed alongside skills (.claude/skills/references/, .agents/skills/references/) | --- | D3 | --- | tests/install_sh/test_references_rsync.py | --- |
| skill-workflow.8 | Shared References Library | references/ is not auto-discovered as a skill | --- | D3 | --- | tests/install_sh/test_references_rsync.py | --- |
| skill-workflow.9 | Shared References Library | Cross-skill reference resolves (cited references/<file>.md exists) | --- | D3 | --- | tests/_shared/test_conftest_helpers.py (assert_references_resolve) | --- |
| skill-workflow.10 | `related:` Frontmatter Key | related: key is parsed without breaking existing frontmatter | --- | D4 | --- | tests/install_sh/test_related_validation.py | --- |
| skill-workflow.11 | `related:` Frontmatter Key | install.sh warns on unknown related target (exit code 0) | --- | D4 | --- | tests/install_sh/test_related_validation.py | --- |
| skill-workflow.12 | `related:` Frontmatter Key | related: key is optional (no warning when omitted) | --- | D4 | --- | tests/install_sh/test_related_validation.py | --- |
| skill-workflow.13 | Content-Invariant Test Framework | Frontmatter parse failure caught by tests | --- | D2 | --- | tests/_shared/test_conftest_helpers.py | --- |
| skill-workflow.14 | Content-Invariant Test Framework | Missing tail block caught for user-invocable skills | --- | D2 | --- | tests/_shared/test_conftest_helpers.py | --- |
| skill-workflow.15 | Content-Invariant Test Framework | Reference cross-link rot caught (assert_references_resolve) | --- | D2 | --- | tests/_shared/test_conftest_helpers.py | --- |
| skill-workflow.16 | Content-Invariant Test Framework | Test paths registered in pyproject (≥18 new test directories collected) | --- | D2 | --- | manual collect-only check at integration | --- |
| skill-workflow.17 | Pattern-Extraction Adaptations | implement-feature contains scope-discipline template (Rules 0-5 + NOTICED BUT NOT TOUCHING) | --- | D6, D7 | --- | tests/implement-feature/test_skill_md.py | --- |
| skill-workflow.18 | Pattern-Extraction Adaptations | simplify contains Chesterton's Fence pre-check + Rule of 500 | --- | D6 | --- | tests/simplify/test_skill_md.py | --- |
| skill-workflow.19 | Pattern-Extraction Adaptations | security-review contains preventive mode (alongside scanner runner) | --- | D6 | --- | tests/security-review/test_skill_md.py | --- |
| skill-workflow.20 | Review Findings Schema Extension | New finding includes axis (5-enum) and severity (5-enum) | parallel-infrastructure/schemas/review-findings.schema.json | --- | --- | tests/parallel-infrastructure/test_review_findings_schema.py | --- |
| skill-workflow.21 | Review Findings Schema Extension | Schema validation rejects missing axis or severity | parallel-infrastructure/schemas/review-findings.schema.json | --- | --- | tests/parallel-infrastructure/test_review_findings_schema.py | --- |
| skill-workflow.22 | Review Findings Schema Extension | Pre-existing required fields and enum values preserved | parallel-infrastructure/schemas/review-findings.schema.json | --- | --- | tests/parallel-infrastructure/test_review_findings_schema.py | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Extend skill-workflow capability rather than create engineering-methodology | --- | Avoids splitting related requirements across two specs; capability already houses skill conventions |
| D2 | Tail-block enforced via content invariants (tests), CI lint deferred | --- | Reuses existing pytest CI surface; failing test catches violations; one-pipeline enforcement |
| D3 | references/ as sibling library, not a skill | --- | Resources have no frontmatter/triggers/user_invocable semantics; modeling as skill would require fake metadata |
| D4 | related: is advisory; requires: remains hard dependency | --- | Semantic distinction preserves clean dependency graph; advisory cross-refs aren't deps |
| D5 | Per-skill user_invocable heuristic: true if operator-triggerable, false if pure orchestrator-loaded | --- | Preserves slash-command palette ergonomics while enabling auto-load patterns |
| D6 | Combined ADAPT edit + tail-block addition in same commit per skill | --- | Each ADAPT-target file touched once; cleaner git history; less merge friction |
| D7 | Tasks ordered TDD-first (test before implementation) | --- | Matches plan-feature Step 6 convention; forces RED before GREEN |
| D8 | Cluster decomposition for parallel phases (4 Phase-1, 3 Phase-2 packages) | --- | Disjoint write scopes confirmed by parallel_zones validation; maximizes coordinator-tier parallelism |

## Review Findings Summary

<!-- Populated by /parallel-review-implementation after Phase 3 integration. -->

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 0/22
- **Tests mapped**: 22 requirements have at least one test
- **Evidence collected**: 0/22 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
