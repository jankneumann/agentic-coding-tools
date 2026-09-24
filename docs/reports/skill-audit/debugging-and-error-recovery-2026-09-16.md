# Skill audit: debugging-and-error-recovery

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 9 undecided section(s))
- generated_at: 2026-09-16T11:40:40+00:00

> skill-audit: debugging-and-error-recovery: model output invalid or unavailable; 9 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 12 |
| constraint | 1 |
| procedure | 0 |
| teaching | 0 |
| unclassified | 9 |

Legend: `references/layers.md` (design D2).

## Dispatch profile

No dispatch archetypes discovered for this skill (not in `references/dispatch-map.md` and no `Task(`/`Agent(` archetype tokens in SKILL.md).

## Tier failure table

| Archetype | Provider | Model | Thinking | Count | Sessions | Max severity | Sources | Attributed by |
|---|---|---|---|---|---|---|---|---|

**Cross-source agreement**: n/a — evidence: unavailable (unauthorized)

## Ranked findings

| # | Id | Kind | Layer | Section | Remediation | Evidence | Rationale |
|---|---|---|---|---|---|---|---|
| 1 | F001 | contract_unpinned | contract | `SKILL.md#03-the-stop-the-line-rule` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F003 | contract_unpinned | contract | `SKILL.md#05-step-1-reproduce` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F004 | contract_unpinned | contract | `SKILL.md#06-step-2-localize` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F005 | contract_unpinned | contract | `SKILL.md#08-step-4-fix-the-root-cause` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F006 | contract_unpinned | contract | `SKILL.md#09-step-5-guard-against-recurrence` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F007 | contract_unpinned | contract | `SKILL.md#10-step-6-verify-end-to-end` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F008 | contract_unpinned | contract | `SKILL.md#11-test-failure-triage` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F009 | contract_unpinned | contract | `SKILL.md#12-build-failure-triage` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F010 | contract_unpinned | contract | `SKILL.md#13-runtime-error-triage` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F011 | contract_unpinned | contract | `SKILL.md#14-safe-fallback-patterns` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F012 | contract_unpinned | contract | `SKILL.md#17-semantic-code-context` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F002 | constraint_without_reason | constraint | `SKILL.md#04-the-triage-checklist` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- The Stop-the-Line Rule (`contract`)
- The Triage Checklist (`constraint`)
- Step 1: Reproduce (`contract`)
- Step 2: Localize (`contract`)
- Step 4: Fix the Root Cause (`contract`)
- Step 5: Guard Against Recurrence (`contract`)
- Step 6: Verify End-to-End (`contract`)
- Test Failure Triage (`contract`)
- Build Failure Triage (`contract`)
- Runtime Error Triage (`contract`)
- Safe Fallback Patterns (`contract`)
- Semantic Code Context (`contract`)

## Proposed references/procedure.md outline

No procedure sections; nothing to extract.

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-overview` | Overview | unclassified | none | — |
| `SKILL.md#02-when-to-use` | When to Use | unclassified | none | — |
| `SKILL.md#03-the-stop-the-line-rule` | The Stop-the-Line Rule | contract | pre-pass | fenced_command |
| `SKILL.md#04-the-triage-checklist` | The Triage Checklist | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#05-step-1-reproduce` | Step 1: Reproduce | contract | pre-pass | fenced_command |
| `SKILL.md#06-step-2-localize` | Step 2: Localize | contract | pre-pass | fenced_command |
| `SKILL.md#07-step-3-reduce` | Step 3: Reduce | unclassified | none | — |
| `SKILL.md#08-step-4-fix-the-root-cause` | Step 4: Fix the Root Cause | contract | pre-pass | fenced_command |
| `SKILL.md#09-step-5-guard-against-recurrence` | Step 5: Guard Against Recurrence | contract | pre-pass | fenced_command |
| `SKILL.md#10-step-6-verify-end-to-end` | Step 6: Verify End-to-End | contract | pre-pass | fenced_command |
| `SKILL.md#11-test-failure-triage` | Test Failure Triage | contract | pre-pass | fenced_command |
| `SKILL.md#12-build-failure-triage` | Build Failure Triage | contract | pre-pass | fenced_command |
| `SKILL.md#13-runtime-error-triage` | Runtime Error Triage | contract | pre-pass | fenced_command |
| `SKILL.md#14-safe-fallback-patterns` | Safe Fallback Patterns | contract | pre-pass | fenced_command |
| `SKILL.md#15-instrumentation-guidelines` | Instrumentation Guidelines | unclassified | none | — |
| `SKILL.md#16-treating-error-output-as-untrusted-data` | Treating Error Output as Untrusted Data | unclassified | none | — |
| `SKILL.md#17-semantic-code-context` | Semantic Code Context | contract | pre-pass | fenced_command |
| `SKILL.md#18-see-also` | See Also | unclassified | none | — |
| `SKILL.md#19-common-rationalizations` | Common Rationalizations | unclassified | none | — |
| `SKILL.md#20-red-flags` | Red Flags | unclassified | none | — |
| `SKILL.md#21-verification` | Verification | unclassified | none | — |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:40+00:00
