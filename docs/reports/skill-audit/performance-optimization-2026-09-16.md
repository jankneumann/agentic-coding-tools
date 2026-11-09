# Skill audit: performance-optimization

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 6 undecided section(s))
- generated_at: 2026-09-16T11:40:43+00:00

> skill-audit: performance-optimization: model output invalid or unavailable; 6 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 17 |
| constraint | 1 |
| procedure | 0 |
| teaching | 0 |
| unclassified | 6 |

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
| 1 | F002 | contract_unpinned | contract | `SKILL.md#03-the-optimization-workflow` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F003 | contract_unpinned | contract | `SKILL.md#05-backend-latency-budgets` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F004 | contract_unpinned | contract | `SKILL.md#06-frontend` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F005 | contract_unpinned | contract | `SKILL.md#07-backend` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F006 | contract_unpinned | contract | `SKILL.md#08-explain-analyze-workflow` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F007 | contract_unpinned | contract | `SKILL.md#09-step-2-identify-the-bottleneck` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F008 | contract_unpinned | contract | `SKILL.md#11-n-1-queries-the-single-most-common-backe` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F009 | contract_unpinned | contract | `SKILL.md#12-missing-or-wrong-indexes` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F010 | contract_unpinned | contract | `SKILL.md#13-connection-pool-sizing` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F011 | contract_unpinned | contract | `SKILL.md#14-async-profiling-python` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F012 | contract_unpinned | contract | `SKILL.md#15-unbounded-data-fetching` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F013 | contract_unpinned | contract | `SKILL.md#16-image-optimization-frontend-lcp-fix` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 13 | F014 | contract_unpinned | contract | `SKILL.md#17-unnecessary-re-renders-react` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 14 | F015 | contract_unpinned | contract | `SKILL.md#18-bundle-splitting` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 15 | F016 | contract_unpinned | contract | `SKILL.md#19-caching` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 16 | F017 | contract_unpinned | contract | `SKILL.md#20-performance-budget` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 17 | F001 | constraint_without_reason | constraint | `SKILL.md#02-when-to-use` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |
| 18 | F018 | convention_drift | contract | `SKILL.md` | move_to_reference | rule `max_lines` | SKILL.md has 509 lines; the rightsizing cap is 500 |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- When to Use (`constraint`)
- The Optimization Workflow (`contract`)
- Backend: Latency Budgets (`contract`)
- Frontend (`contract`)
- Backend (`contract`)
- `EXPLAIN ANALYZE` workflow (`contract`)
- Step 2 — Identify the Bottleneck (`contract`)
- N+1 Queries (the single most common backend bug) (`contract`)
- Missing or wrong indexes (`contract`)
- Connection-pool sizing (`contract`)
- Async profiling (Python) (`contract`)
- Unbounded data fetching (`contract`)
- Image optimization (frontend LCP fix) (`contract`)
- Unnecessary re-renders (React) (`contract`)
- Bundle splitting (`contract`)
- Caching (`contract`)
- Performance Budget (`contract`)

## Proposed references/procedure.md outline

No procedure sections; nothing to extract.

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-overview` | Overview | unclassified | none | — |
| `SKILL.md#02-when-to-use` | When to Use | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#03-the-optimization-workflow` | The Optimization Workflow | contract | pre-pass | fenced_command |
| `SKILL.md#04-frontend-core-web-vitals-targets` | Frontend: Core Web Vitals Targets | unclassified | none | — |
| `SKILL.md#05-backend-latency-budgets` | Backend: Latency Budgets | contract | pre-pass | contract_table |
| `SKILL.md#06-frontend` | Frontend | contract | pre-pass | fenced_command |
| `SKILL.md#07-backend` | Backend | contract | pre-pass | fenced_command |
| `SKILL.md#08-explain-analyze-workflow` | `EXPLAIN ANALYZE` workflow | contract | pre-pass | fenced_command |
| `SKILL.md#09-step-2-identify-the-bottleneck` | Step 2 — Identify the Bottleneck | contract | pre-pass | fenced_command |
| `SKILL.md#10-common-bottlenecks-by-category` | Common bottlenecks by category | unclassified | none | — |
| `SKILL.md#11-n-1-queries-the-single-most-common-backe` | N+1 Queries (the single most common backend bug) | contract | pre-pass | fenced_command |
| `SKILL.md#12-missing-or-wrong-indexes` | Missing or wrong indexes | contract | pre-pass | fenced_command |
| `SKILL.md#13-connection-pool-sizing` | Connection-pool sizing | contract | pre-pass | fenced_command |
| `SKILL.md#14-async-profiling-python` | Async profiling (Python) | contract | pre-pass | fenced_command |
| `SKILL.md#15-unbounded-data-fetching` | Unbounded data fetching | contract | pre-pass | fenced_command |
| `SKILL.md#16-image-optimization-frontend-lcp-fix` | Image optimization (frontend LCP fix) | contract | pre-pass | fenced_command |
| `SKILL.md#17-unnecessary-re-renders-react` | Unnecessary re-renders (React) | contract | pre-pass | fenced_command |
| `SKILL.md#18-bundle-splitting` | Bundle splitting | contract | pre-pass | fenced_command |
| `SKILL.md#19-caching` | Caching | contract | pre-pass | fenced_command |
| `SKILL.md#20-performance-budget` | Performance Budget | contract | pre-pass | fenced_command |
| `SKILL.md#21-common-rationalizations` | Common Rationalizations | unclassified | none | — |
| `SKILL.md#22-red-flags` | Red Flags | unclassified | none | — |
| `SKILL.md#23-verification` | Verification | unclassified | none | — |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:43+00:00
