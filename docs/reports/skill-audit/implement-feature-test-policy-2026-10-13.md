# Skill audit, test-policy lens: implement-feature

- lens: test-policy
- generated_at: 2026-10-13T00:00:00+00:00
- instructions: 12
- findings: 0

Findings are proposals; the lens never edits the audited skill. This report is not the rightsizing audit and does not count as the skill's freshness report.

## Findings

No test-policy findings.

## Instructions

| section | oracle_source | authorship | instruction |
|---|---|---|---|
| SKILL.md#12-implementation-rules-0-5 | unclassified | unclassified | **Rule 2 — Keep It Compilable.** Every commit on the feature branch must build and pass existing tests. |
| SKILL.md#15-3a-generate-change-context-test-plan-pha | unclassified | unclassified | Before implementing, create the traceability skeleton and write failing tests: |
| SKILL.md#15-3a-generate-change-context-test-plan-pha | unclassified | unclassified | Write failing tests (RED) for each row in the matrix. |
| SKILL.md#15-3a-generate-change-context-test-plan-pha | unclassified | unclassified | Tests MUST assert against contract schemas and design decisions where referenced — not just internal behavior. |
| SKILL.md#20-local-parallel-tier-local-parallel | unclassified | unclassified | Update Coverage Summary counts |
| SKILL.md#25-per-package-context-checkpoint-local-par | unclassified | unclassified | The last two both skip the checkpoint, and reporting them the same way is the failure this rule exists to prevent: an... |
| SKILL.md#29-6-4-live-service-smoke-tests-soft-gate-a | unclassified | unclassified | Run live service smoke tests if a test environment is available: |
| SKILL.md#30-6-5-artifact-validation-local-parallel | unclassified | unclassified | This runs the canonical validation skill targeting: - **Spec compliance** (`spec` phase): Audits `change-context.md`... |
| SKILL.md#33-8-commit-changes-all-tiers | unclassified | unclassified | **Conventional commit format**: `feat(scope):`, `fix(scope):`, `test(scope):`, `docs(scope):` |
| SKILL.md#37-output | unclassified | unclassified | All tests passing |
| SKILL.md#38-next-step | impl_derived | unspecified | Keep simplify work as separate `refactor(...)` commits (and optional leading `test(...): pin behavior…` characterizat... |
| SKILL.md#41-verification | unclassified | unclassified | Show that every commit on the branch builds and passes tests in isolation: `git log --oneline main..HEAD` followed by... |
