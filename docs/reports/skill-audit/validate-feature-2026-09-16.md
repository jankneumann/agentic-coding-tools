# Skill audit: validate-feature

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 7 undecided section(s))
- generated_at: 2026-09-16T11:40:34+00:00

> skill-audit: validate-feature: model output invalid or unavailable; 7 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 29 |
| constraint | 0 |
| procedure | 0 |
| teaching | 0 |
| unclassified | 7 |

Legend: `references/layers.md` (design D2).

## Dispatch profile

| Archetype | Tier | Provider | Model | Thinking | Procedure mode | Degraded from | Phases |
|---|---|---|---|---|---|---|---|
| validator | standard | claude_code | sonnet | — | — | — | VALIDATE |
| validator | standard | codex | gpt-5.6-terra | — | — | — | VALIDATE |
| validator | standard | antigravity | gemini-3.6-flash-medium | — | — | — | VALIDATE |
| validator | standard | grok | grok-4.5 | medium | — | — | VALIDATE |
| validator | standard | pi | qwen/qwen3-coder | — | — | — | VALIDATE |
| validator | standard | local | gpt-oss-120b | — | — | — | VALIDATE |
| implementer | standard | claude_code | sonnet | — | — | — | VAL_FIX |
| implementer | standard | codex | gpt-5.6-terra | — | — | — | VAL_FIX |
| implementer | standard | antigravity | gemini-3.6-flash-medium | — | — | — | VAL_FIX |
| implementer | standard | grok | grok-4.5 | medium | — | — | VAL_FIX |
| implementer | standard | pi | qwen/qwen3-coder | — | — | — | VAL_FIX |
| implementer | standard | local | gpt-oss-120b | — | — | — | VAL_FIX |

## Tier failure table

| Archetype | Provider | Model | Thinking | Count | Sessions | Max severity | Sources | Attributed by |
|---|---|---|---|---|---|---|---|---|

**Cross-source agreement**: n/a — evidence: unavailable (unauthorized)

## Ranked findings

| # | Id | Kind | Layer | Section | Remediation | Evidence | Rationale |
|---|---|---|---|---|---|---|---|
| 1 | F001 | contract_unpinned | contract | `SKILL.md#00-frontmatter` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F002 | contract_unpinned | contract | `SKILL.md#08-0-detect-coordinator-and-recall-memory` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F003 | contract_unpinned | contract | `SKILL.md#14-4-smoke-phase` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F004 | contract_unpinned | contract | `SKILL.md#17-6-e2e-phase` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F005 | contract_unpinned | contract | `SKILL.md#24-8-log-analysis-phase` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F006 | contract_unpinned | contract | `SKILL.md#25-9-ci-cd-status-phase` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F007 | contract_unpinned | contract | `SKILL.md#26-10-teardown` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F008 | contract_unpinned | contract | `SKILL.md#29-12-5-finalize-ephemeral-validation-scope` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F009 | contract_unpinned | contract | `SKILL.md#30-13-pr-comment` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F010 | contract_unpinned | contract | `SKILL.md#32-after-validation` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F011 | contract_unpinned | contract | `SKILL.md#35-next-step` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F012 | convention_drift | contract | `SKILL.md` | move_to_reference | rule `max_lines` | SKILL.md has 1289 lines; the rightsizing cap is 500 |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- Local CLI Mutation Boundary (`contract`)
- 0. Detect Coordinator and Recall Memory (`contract`)
- 1. Determine Change ID and Configuration (`contract`)
- 2. Verify Prerequisites (`contract`)
- 2.25. Enter Ephemeral Validation Scope (Optional) (`contract`)
- 2.5. Prepare Validation Artifacts (`contract`)
- 3. Deploy Phase (`contract`)
- 4. Smoke Phase (`contract`)
- 4b. Gen-Eval Phase (Optional) (`contract`)
- 5. Security Phase (`contract`)
- 6. E2E Phase (`contract`)
- 6b. Architecture Diagnostics Phase (`contract`)
- 7.0. Task Checkbox Drift Gate (CRITICAL) (`contract`)
- 7.0b. Requirement-to-Contract Traceability Gate (CRITICAL, change-scoped) (`contract`)
- 7.1. Requirement Traceability (per-requirement live verification) (`contract`)
- 7.5. Work Package Evidence Completeness [local-parallel+] (`contract`)
- 8. Log Analysis Phase (`contract`)
- 9. CI/CD Status Phase (`contract`)
- 10. Teardown (`contract`)
- 11. Validation Report (`contract`)
- 12. Persist Report (`contract`)
- 12.5. Finalize Ephemeral Validation Scope (`contract`)
- 13. PR Comment (`contract`)
- 14. Append Session Log (`contract`)
- After Validation (`contract`)
- Semantic Code Context (`contract`)
- Output (`contract`)
- Next Step (`contract`)

## Proposed references/procedure.md outline

No procedure sections; nothing to extract.

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-durable-state-artifact-authority` | Durable state artifact authority | unclassified | none | — |
| `SKILL.md#02-arguments` | Arguments | unclassified | none | — |
| `SKILL.md#03-prerequisites` | Prerequisites | unclassified | none | — |
| `SKILL.md#04-provider-neutral-dispatch` | Provider-Neutral Dispatch | unclassified | none | — |
| `SKILL.md#05-openspec-execution-preference` | OpenSpec Execution Preference | unclassified | none | — |
| `SKILL.md#06-coordinator-integration-optional` | Coordinator Integration (Optional) | unclassified | none | — |
| `SKILL.md#07-local-cli-mutation-boundary` | Local CLI Mutation Boundary | contract | pre-pass | fenced_command |
| `SKILL.md#08-0-detect-coordinator-and-recall-memory` | 0. Detect Coordinator and Recall Memory | contract | pre-pass | skill_base_dir |
| `SKILL.md#09-1-determine-change-id-and-configuration` | 1. Determine Change ID and Configuration | contract | pre-pass | fenced_command |
| `SKILL.md#10-2-verify-prerequisites` | 2. Verify Prerequisites | contract | pre-pass | fenced_command |
| `SKILL.md#11-2-25-enter-ephemeral-validation-scope-op` | 2.25. Enter Ephemeral Validation Scope (Optional) | contract | pre-pass | fenced_command |
| `SKILL.md#12-2-5-prepare-validation-artifacts` | 2.5. Prepare Validation Artifacts | contract | pre-pass | fenced_command |
| `SKILL.md#13-3-deploy-phase` | 3. Deploy Phase | contract | pre-pass | fenced_command |
| `SKILL.md#14-4-smoke-phase` | 4. Smoke Phase | contract | pre-pass | fenced_command |
| `SKILL.md#15-4b-gen-eval-phase-optional` | 4b. Gen-Eval Phase (Optional) | contract | pre-pass | fenced_command |
| `SKILL.md#16-5-security-phase` | 5. Security Phase | contract | pre-pass | fenced_command |
| `SKILL.md#17-6-e2e-phase` | 6. E2E Phase | contract | pre-pass | fenced_command |
| `SKILL.md#18-6b-architecture-diagnostics-phase` | 6b. Architecture Diagnostics Phase | contract | pre-pass | fenced_command |
| `SKILL.md#19-7-spec-compliance-phase-via-change-conte` | 7. Spec Compliance Phase (via Change Context) | unclassified | none | — |
| `SKILL.md#20-7-0-task-checkbox-drift-gate-critical` | 7.0. Task Checkbox Drift Gate (CRITICAL) | contract | pre-pass | fenced_command |
| `SKILL.md#21-7-0b-requirement-to-contract-traceabilit` | 7.0b. Requirement-to-Contract Traceability Gate (CRITICAL, change-scoped) | contract | pre-pass | fenced_command |
| `SKILL.md#22-7-1-requirement-traceability-per-require` | 7.1. Requirement Traceability (per-requirement live verification) | contract | pre-pass | fenced_command |
| `SKILL.md#23-7-5-work-package-evidence-completeness-l` | 7.5. Work Package Evidence Completeness [local-parallel+] | contract | pre-pass | fenced_command |
| `SKILL.md#24-8-log-analysis-phase` | 8. Log Analysis Phase | contract | pre-pass | fenced_command |
| `SKILL.md#25-9-ci-cd-status-phase` | 9. CI/CD Status Phase | contract | pre-pass | fenced_command |
| `SKILL.md#26-10-teardown` | 10. Teardown | contract | pre-pass | fenced_command |
| `SKILL.md#27-11-validation-report` | 11. Validation Report | contract | pre-pass | fenced_command |
| `SKILL.md#28-12-persist-report` | 12. Persist Report | contract | pre-pass | fenced_command |
| `SKILL.md#29-12-5-finalize-ephemeral-validation-scope` | 12.5. Finalize Ephemeral Validation Scope | contract | pre-pass | fenced_command |
| `SKILL.md#30-13-pr-comment` | 13. PR Comment | contract | pre-pass | fenced_command |
| `SKILL.md#31-14-append-session-log` | 14. Append Session Log | contract | pre-pass | fenced_command |
| `SKILL.md#32-after-validation` | After Validation | contract | pre-pass | fenced_command |
| `SKILL.md#33-semantic-code-context` | Semantic Code Context | contract | pre-pass | fenced_command |
| `SKILL.md#34-output` | Output | contract | pre-pass | skill_base_dir |
| `SKILL.md#35-next-step` | Next Step | contract | pre-pass | fenced_command |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:34+00:00
