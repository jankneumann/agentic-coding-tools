# Skill audit, test-policy lens: simplify

- lens: test-policy
- generated_at: 2026-10-13T00:00:00+00:00
- instructions: 21
- findings: 4

Findings are proposals; the lens never edits the audited skill. This report is not the rightsizing audit and does not count as the skill's freshness report.

## Findings

| id | kind | section | remediation | rationale |
|---|---|---|---|---|
| F001 | test_coverage_target | SKILL.md#01-simplify | add_reason | line coverage is used as a goal or gate (1 instruction(s)): "This skill is **read → pin → edit**: it reviews first, applies a **coverage gate**, writes characterization tests when needed, gates each candidate against C..." |
| F002 | test_coverage_target | SKILL.md#04-scope | add_reason | line coverage is used as a goal or gate (1 instruction(s)): "Production edits only after the coverage gate passes." |
| F003 | test_coverage_target | SKILL.md#27-red-flags | add_reason | line coverage is used as a goal or gate (1 instruction(s)): "Production simplify commits without a coverage-gate decision (existing pins **or** new characterization tests)." |
| F004 | test_coverage_target | SKILL.md#28-verification | add_reason | line coverage is used as a goal or gate (1 instruction(s)): "Confirm coverage gate: either list existing pinning tests **or** show the characterization commit (`test(...): pin behavior…`) that is green on baseline." |

## Instructions

| section | oracle_source | authorship | instruction |
|---|---|---|---|
| SKILL.md#01-simplify | impl_derived | unspecified | This skill is **read → pin → edit**: it reviews first, applies a **coverage gate**, writes characterization tests whe... |
| SKILL.md#04-scope | unspecified | unspecified | Production edits only after the coverage gate passes. |
| SKILL.md#04-scope | impl_derived | unspecified | Characterization commits may add tests; simplify commits must not change assertion **bodies**. |
| SKILL.md#06-2-tests-are-the-isomorphism-proof | unclassified | unclassified | Observable equivalence is proven by behavioral tests, not by agent confidence. |
| SKILL.md#06-2-tests-are-the-isomorphism-proof | unclassified | unclassified | Prefer **state-based** tests (inputs/outputs) over interaction mocks so structure can move without rewriting tests —... |
| SKILL.md#10-chesterton-s-fence-pre-simplification-ch | unclassified | unclassified | **Why does this exist?** `git blame`, introducing commit message, callers (`grep`), tests that pin it. |
| SKILL.md#11-coverage-gate-required | impl_derived | unspecified | Characterization tests are **not** a license to change behavior later in the same PR — they freeze today's behavior s... |
| SKILL.md#15-0-scope | impl_derived | unspecified | Record the **baseline SHA** (tip before any simplify production edit; after characterization commits if those land fi... |
| SKILL.md#16-1-understand-chesterton-s-fence | unclassified | unclassified | Blame, callers, existing tests, edge cases. |
| SKILL.md#17-2-coverage-gate | impl_derived | unspecified | Pin or characterize (see above). |
| SKILL.md#17-2-coverage-gate | impl_derived | unspecified | Run characterization tests and confirm green on baseline. |
| SKILL.md#21-6-dual-run-verify | unclassified | unclassified | Source-contribution-only example (this monorepo, not portable to consumers): `skills/.venv/bin/python -m pytest -q sk... |
| SKILL.md#22-7-report | impl_derived | unspecified | Summarize: patterns applied, fences kept, characterization tests added, dual-run evidence (commands + exit codes or r... |
| SKILL.md#23-script-helpers | impl_derived | unspecified | `check_test_contract.py` expects `--base` at the tip **after** characterization commits. |
| SKILL.md#23-script-helpers | unclassified | unclassified | Within that range, any `+/-` assertion line (including deleted test files) is a contract break. |
| SKILL.md#23-script-helpers | unclassified | unclassified | `verify_behavior_preservation.py` takes a **trusted** `--test-cmd` shell string (e.g. `pytest -q`). |
| SKILL.md#27-red-flags | impl_derived | unspecified | Production simplify commits without a coverage-gate decision (existing pins **or** new characterization tests). |
| SKILL.md#27-red-flags | unclassified | unclassified | A simplify PR that changes test assertion bodies to go green. |
| SKILL.md#27-red-flags | unclassified | unclassified | Isomorphic extract landed without tests covering all rewritten call sites. |
| SKILL.md#28-verification | impl_derived | unspecified | Confirm coverage gate: either list existing pinning tests **or** show the characterization commit (`test(...): pin be... |
| SKILL.md#28-verification | impl_derived | unspecified | Confirm assertion contract: `check_test_contract.py --base <baseline>` exits 0 for the simplify range (characterizati... |
