# Skill audit: merge-pull-requests

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 19 undecided section(s))
- generated_at: 2026-09-16T11:40:31+00:00

> skill-audit: merge-pull-requests: model output invalid or unavailable; 19 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 29 |
| constraint | 5 |
| procedure | 1 |
| teaching | 0 |
| unclassified | 19 |

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
| 1 | F001 | contract_unpinned | contract | `SKILL.md#05-active-agent-guard-sync-point-skill` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F003 | contract_unpinned | contract | `SKILL.md#12-1-verify-environment` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F004 | contract_unpinned | contract | `SKILL.md#13-2-pull-latest-main` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F005 | contract_unpinned | contract | `SKILL.md#15-draft-prs` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F006 | contract_unpinned | contract | `SKILL.md#19-5-check-staleness-for-each-pr` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F007 | contract_unpinned | contract | `SKILL.md#21-6-identify-conflicting-pr-pairs` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F008 | contract_unpinned | contract | `SKILL.md#22-7-batch-close-obsolete-prs` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F009 | contract_unpinned | contract | `SKILL.md#23-8-analyze-review-comments` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F010 | contract_unpinned | contract | `SKILL.md#26-9-6-check-holdout-gate-openspec-prs-only` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F012 | contract_unpinned | contract | `SKILL.md#29-save-point-pattern` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F013 | contract_unpinned | contract | `SKILL.md#30-change-summary-template` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F014 | contract_unpinned | contract | `SKILL.md#34-re-check-staleness-after-merge` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 13 | F015 | contract_unpinned | contract | `SKILL.md#35-close-a-pr` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 14 | F002 | constraint_without_reason | constraint | `SKILL.md#07-merge-metrics-always-on` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |
| 15 | F016 | constraint_without_reason | constraint | `SKILL.md#40-guards-in-enforcement-order` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |
| 16 | F017 | constraint_without_reason | constraint | `SKILL.md#45-ownership-boundary` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |
| 17 | F011 | procedure_without_probe | procedure | `SKILL.md#28-11-interactive-pr-review` | add_probe | — | Ordered steps with no acceptance probe; a goal-directed tier cannot tell when it is done. |
| 18 | F018 | missing_deviation_protocol | procedure | `SKILL.md#28-11-interactive-pr-review` | add_probe | — | The skill has procedure but never says how to record a deviation from it. |
| 19 | F019 | convention_drift | contract | `SKILL.md` | move_to_reference | rule `max_lines` | SKILL.md has 1128 lines; the rightsizing cap is 500 |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- Active-Agent Guard (Sync-Point Skill) (`contract`)
- Merge Metrics (always on) (`constraint`)
- Background Merge Watcher (`contract`)
- Default conductor (plan-then-execute) (`contract`)
- Durable Merge Plan and Fresh-Context Execution (`contract`)
- 1. Verify Environment (`contract`)
- 2. Pull Latest Main (`contract`)
- 3. Discover and Classify Open PRs (`--interactive` continues here) (`contract`)
- Draft PRs (`contract`)
- Auto-Merge PRs (`constraint`)
- 5. Check Staleness for Each PR (`contract`)
- 5b. Classify CI Failures (`contract`)
- 6. Identify Conflicting PR Pairs (`contract`)
- 7. Batch Close Obsolete PRs (`contract`)
- 8. Analyze Review Comments (`contract`)
- 9. Conditional Multi-Vendor Review (`contract`)
- 9.5. Merge-Time Validation Gate for OpenSpec PRs (`contract`)
- 9.6. Check Holdout Gate (OpenSpec PRs Only) (`contract`)
- Save Point Pattern (`contract`)
- Change Summary template (`contract`)
- Merge a PR (`contract`)
- Re-run Failed CI Checks (`contract`)
- Re-check Staleness After Merge (`contract`)
- Close a PR (`contract`)
- 11.5. Post-Merge OpenSpec Cleanup Approval (`contract`)
- Phases (`contract`)
- Guards, in enforcement order (`constraint`)
- Outcomes (`contract`)
- Semantic index (`constraint`)
- Ownership boundary (`constraint`)
- 12. Summary (`contract`)
- 13. Append Merge Log (`contract`)
- Dry-Run Mode (`contract`)
- Procedure: one line pointing at `references/procedure.md`

## Proposed references/procedure.md outline

- 11. Interactive PR Review (6 step(s), from `SKILL.md#28-11-interactive-pr-review`)

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-merge-pull-requests` | Merge Pull Requests | unclassified | none | — |
| `SKILL.md#02-arguments` | Arguments | unclassified | none | — |
| `SKILL.md#03-script-location` | Script Location | unclassified | none | — |
| `SKILL.md#04-prerequisites` | Prerequisites | unclassified | none | — |
| `SKILL.md#05-active-agent-guard-sync-point-skill` | Active-Agent Guard (Sync-Point Skill) | contract | pre-pass | fenced_command |
| `SKILL.md#06-merge-backend-selection` | Merge Backend Selection | unclassified | none | — |
| `SKILL.md#07-merge-metrics-always-on` | Merge Metrics (always on) | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#08-post-merge-pipeline` | Post-Merge Pipeline | unclassified | none | — |
| `SKILL.md#09-background-merge-watcher` | Background Merge Watcher | contract | pre-pass | fenced_command |
| `SKILL.md#10-default-conductor-plan-then-execute` | Default conductor (plan-then-execute) | contract | pre-pass | fenced_command |
| `SKILL.md#11-durable-merge-plan-and-fresh-context-exe` | Durable Merge Plan and Fresh-Context Execution | contract | pre-pass | fenced_command |
| `SKILL.md#12-1-verify-environment` | 1. Verify Environment | contract | pre-pass | fenced_command |
| `SKILL.md#13-2-pull-latest-main` | 2. Pull Latest Main | contract | pre-pass | fenced_command |
| `SKILL.md#14-3-discover-and-classify-open-prs-interac` | 3. Discover and Classify Open PRs (`--interactive` continues here) | contract | pre-pass | fenced_command |
| `SKILL.md#15-draft-prs` | Draft PRs | contract | pre-pass | fenced_command |
| `SKILL.md#16-stacked-prs` | Stacked PRs | unclassified | none | — |
| `SKILL.md#17-fork-prs` | Fork PRs | unclassified | none | — |
| `SKILL.md#18-auto-merge-prs` | Auto-Merge PRs | constraint | pre-pass | constraint |
| `SKILL.md#19-5-check-staleness-for-each-pr` | 5. Check Staleness for Each PR | contract | pre-pass | fenced_command |
| `SKILL.md#20-5b-classify-ci-failures` | 5b. Classify CI Failures | contract | pre-pass | fenced_command |
| `SKILL.md#21-6-identify-conflicting-pr-pairs` | 6. Identify Conflicting PR Pairs | contract | pre-pass | fenced_command |
| `SKILL.md#22-7-batch-close-obsolete-prs` | 7. Batch Close Obsolete PRs | contract | pre-pass | fenced_command |
| `SKILL.md#23-8-analyze-review-comments` | 8. Analyze Review Comments | contract | pre-pass | fenced_command |
| `SKILL.md#24-9-conditional-multi-vendor-review` | 9. Conditional Multi-Vendor Review | contract | pre-pass | fenced_command |
| `SKILL.md#25-9-5-merge-time-validation-gate-for-opens` | 9.5. Merge-Time Validation Gate for OpenSpec PRs | contract | pre-pass | fenced_command |
| `SKILL.md#26-9-6-check-holdout-gate-openspec-prs-only` | 9.6. Check Holdout Gate (OpenSpec PRs Only) | contract | pre-pass | fenced_command |
| `SKILL.md#27-10-determine-merge-order` | 10. Determine Merge Order | unclassified | none | — |
| `SKILL.md#28-11-interactive-pr-review` | 11. Interactive PR Review | procedure | pre-pass | procedure |
| `SKILL.md#29-save-point-pattern` | Save Point Pattern | contract | pre-pass | fenced_command |
| `SKILL.md#30-change-summary-template` | Change Summary template | contract | pre-pass | fenced_command |
| `SKILL.md#31-merge-strategy-selection` | Merge Strategy Selection | unclassified | none | — |
| `SKILL.md#32-merge-a-pr` | Merge a PR | contract | pre-pass | fenced_command |
| `SKILL.md#33-re-run-failed-ci-checks` | Re-run Failed CI Checks | contract | pre-pass | fenced_command |
| `SKILL.md#34-re-check-staleness-after-merge` | Re-check Staleness After Merge | contract | pre-pass | fenced_command |
| `SKILL.md#35-close-a-pr` | Close a PR | contract | pre-pass | fenced_command |
| `SKILL.md#36-address-comments` | Address Comments | unclassified | none | — |
| `SKILL.md#37-11-5-post-merge-openspec-cleanup-approva` | 11.5. Post-Merge OpenSpec Cleanup Approval | contract | pre-pass | fenced_command |
| `SKILL.md#38-11-6-main-context-convergence` | 11.6. Main Context Convergence | unclassified | none | — |
| `SKILL.md#39-phases` | Phases | contract | pre-pass | fenced_command |
| `SKILL.md#40-guards-in-enforcement-order` | Guards, in enforcement order | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#41-identity-and-idempotence` | Identity and idempotence | unclassified | none | — |
| `SKILL.md#42-outcomes` | Outcomes | contract | pre-pass | contract_table |
| `SKILL.md#43-semantic-index` | Semantic index | constraint | pre-pass | constraint |
| `SKILL.md#44-what-lands-and-what-stays-untracked` | What lands, and what stays untracked | unclassified | none | — |
| `SKILL.md#45-ownership-boundary` | Ownership boundary | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#46-12-summary` | 12. Summary | contract | pre-pass | fenced_command |
| `SKILL.md#47-13-append-merge-log` | 13. Append Merge Log | contract | pre-pass | fenced_command |
| `SKILL.md#48-dry-run-mode` | Dry-Run Mode | contract | pre-pass | fenced_command |
| `SKILL.md#49-output` | Output | unclassified | none | — |
| `SKILL.md#50-error-handling` | Error Handling | unclassified | none | — |
| `SKILL.md#51-common-rationalizations` | Common Rationalizations | unclassified | none | — |
| `SKILL.md#52-red-flags` | Red Flags | unclassified | none | — |
| `SKILL.md#53-verification` | Verification | unclassified | none | — |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:31+00:00
