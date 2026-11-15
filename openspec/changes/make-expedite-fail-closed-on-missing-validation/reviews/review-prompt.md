Review the implementation of OpenSpec change `make-expedite-fail-closed-on-missing-validation` on this branch (PR #702).
This is a stacked PR; its base is `origin/openspec/adopt-verification-enforcement-discipline`, NOT main.

Scope (read only these):
- Run: git diff origin/openspec/adopt-verification-enforcement-discipline...HEAD -- skills/expedite docs/mental-models.md openspec/changes/make-expedite-fail-closed-on-missing-validation/work-packages.yaml
- Requirements: openspec/changes/make-expedite-fail-closed-on-missing-validation/proposal.md, design.md, specs/expedite/spec.md
Ignore session logs, handoffs, loop-state, review caches and ledgers.

Focus on: correctness of the fail-closed validation_report check and the --accept-missing-validation override,
spec compliance, test adequacy (including skills/expedite/scripts/tests/test_skill_md_drift.py), and security.
Output ONLY valid JSON conforming to review-findings.schema.json.
