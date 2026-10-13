# Skill audit, test-policy lens: iterate-on-implementation

- lens: test-policy
- generated_at: 2026-10-13T00:00:00+00:00
- instructions: 5
- findings: 1

Findings are proposals; the lens never edits the audited skill. This report is not the rightsizing audit and does not count as the skill's freshness report.

## Findings

| id | kind | section | remediation | rationale |
|---|---|---|---|---|
| F001 | test_coverage_target | SKILL.md#32-next-step | add_reason | line coverage is used as a goal or gate (1 instruction(s)): "**Optional polish (manual):** After iterations converge and the suite is green, operators may run `/simplify` on the changed surface for behavior-preserving..." |

## Instructions

| section | oracle_source | authorship | instruction |
|---|---|---|---|
| SKILL.md#21-9-update-openspec-documents | unclassified | unclassified | **`openspec/changes/<change-id>/change-context.md`** — if this iteration added new files, tests, or changed requireme... |
| SKILL.md#21-9-update-openspec-documents | unclassified | unclassified | Update Coverage Summary if new tests were added or requirements were discovered. |
| SKILL.md#21-9-update-openspec-documents | unclassified | unclassified | If a finding reveals a missing spec requirement, add a new row to the matrix and write the corresponding test before... |
| SKILL.md#28-11-5-audit-choices-non-blocking | unclassified | unclassified | It MUST NOT be invoked inside a bash fence, via command substitution (`$(...)`), or have its exit status tested with... |
| SKILL.md#32-next-step | unspecified | unspecified | **Optional polish (manual):** After iterations converge and the suite is green, operators may run `/simplify` on the... |
