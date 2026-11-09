# Skill audit: test-driven-development

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 9 undecided section(s))
- generated_at: 2026-09-16T11:40:37+00:00

> skill-audit: test-driven-development: model output invalid or unavailable; 9 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 17 |
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
| 1 | F001 | contract_unpinned | contract | `SKILL.md#03-the-tdd-cycle` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F002 | contract_unpinned | contract | `SKILL.md#04-step-1-red-write-a-failing-test` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F003 | contract_unpinned | contract | `SKILL.md#05-step-2-green-make-it-pass` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F004 | contract_unpinned | contract | `SKILL.md#06-step-3-refactor-clean-up` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F005 | contract_unpinned | contract | `SKILL.md#07-the-prove-it-pattern-bug-fixes` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F006 | contract_unpinned | contract | `SKILL.md#08-the-test-pyramid` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F007 | contract_unpinned | contract | `SKILL.md#10-decision-guide` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F008 | contract_unpinned | contract | `SKILL.md#12-test-state-not-interactions` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F009 | contract_unpinned | contract | `SKILL.md#13-damp-over-dry-in-tests` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F010 | contract_unpinned | contract | `SKILL.md#14-prefer-real-implementations-over-mocks` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F011 | contract_unpinned | contract | `SKILL.md#15-use-the-arrange-act-assert-pattern` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F012 | contract_unpinned | contract | `SKILL.md#16-one-assertion-per-concept` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 13 | F013 | contract_unpinned | contract | `SKILL.md#17-name-tests-descriptively` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 14 | F014 | contract_unpinned | contract | `SKILL.md#19-coverage-and-targeted-runs` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 15 | F015 | contract_unpinned | contract | `SKILL.md#20-browser-testing-with-devtools` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 16 | F017 | contract_unpinned | contract | `SKILL.md#22-when-to-use-subagents-for-testing` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 17 | F016 | constraint_without_reason | constraint | `SKILL.md#21-security-boundaries` | add_reason | — | Prohibition without a stated reason; a strong model argues with a bare rule. |
| 18 | F018 | convention_drift | contract | `SKILL.md` | move_to_reference | rule `max_lines` | SKILL.md has 606 lines; the rightsizing cap is 500 |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- The TDD Cycle (`contract`)
- Step 1: RED — Write a Failing Test (`contract`)
- Step 2: GREEN — Make It Pass (`contract`)
- Step 3: REFACTOR — Clean Up (`contract`)
- The Prove-It Pattern (Bug Fixes) (`contract`)
- The Test Pyramid (`contract`)
- Decision Guide (`contract`)
- Test State, Not Interactions (`contract`)
- DAMP Over DRY in Tests (`contract`)
- Prefer Real Implementations Over Mocks (`contract`)
- Use the Arrange-Act-Assert Pattern (`contract`)
- One Assertion Per Concept (`contract`)
- Name Tests Descriptively (`contract`)
- Coverage and Targeted Runs (`contract`)
- Browser Testing with DevTools (`contract`)
- Security Boundaries (`constraint`)
- When to Use Subagents for Testing (`contract`)

## Proposed references/procedure.md outline

No procedure sections; nothing to extract.

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-overview` | Overview | unclassified | none | — |
| `SKILL.md#02-when-to-use` | When to Use | unclassified | none | — |
| `SKILL.md#03-the-tdd-cycle` | The TDD Cycle | contract | pre-pass | fenced_command |
| `SKILL.md#04-step-1-red-write-a-failing-test` | Step 1: RED — Write a Failing Test | contract | pre-pass | fenced_command |
| `SKILL.md#05-step-2-green-make-it-pass` | Step 2: GREEN — Make It Pass | contract | pre-pass | fenced_command |
| `SKILL.md#06-step-3-refactor-clean-up` | Step 3: REFACTOR — Clean Up | contract | pre-pass | fenced_command |
| `SKILL.md#07-the-prove-it-pattern-bug-fixes` | The Prove-It Pattern (Bug Fixes) | contract | pre-pass | fenced_command |
| `SKILL.md#08-the-test-pyramid` | The Test Pyramid | contract | pre-pass | fenced_command |
| `SKILL.md#09-test-sizes-resource-model` | Test Sizes (Resource Model) | unclassified | none | — |
| `SKILL.md#10-decision-guide` | Decision Guide | contract | pre-pass | fenced_command |
| `SKILL.md#11-writing-good-tests` | Writing Good Tests | unclassified | none | — |
| `SKILL.md#12-test-state-not-interactions` | Test State, Not Interactions | contract | pre-pass | fenced_command |
| `SKILL.md#13-damp-over-dry-in-tests` | DAMP Over DRY in Tests | contract | pre-pass | fenced_command |
| `SKILL.md#14-prefer-real-implementations-over-mocks` | Prefer Real Implementations Over Mocks | contract | pre-pass | fenced_command |
| `SKILL.md#15-use-the-arrange-act-assert-pattern` | Use the Arrange-Act-Assert Pattern | contract | pre-pass | fenced_command |
| `SKILL.md#16-one-assertion-per-concept` | One Assertion Per Concept | contract | pre-pass | fenced_command |
| `SKILL.md#17-name-tests-descriptively` | Name Tests Descriptively | contract | pre-pass | fenced_command |
| `SKILL.md#18-test-anti-patterns-to-avoid` | Test Anti-Patterns to Avoid | unclassified | none | — |
| `SKILL.md#19-coverage-and-targeted-runs` | Coverage and Targeted Runs | contract | pre-pass | fenced_command |
| `SKILL.md#20-browser-testing-with-devtools` | Browser Testing with DevTools | contract | pre-pass | fenced_command |
| `SKILL.md#21-security-boundaries` | Security Boundaries | constraint | pre-pass | prohibition_without_reason |
| `SKILL.md#22-when-to-use-subagents-for-testing` | When to Use Subagents for Testing | contract | pre-pass | fenced_command |
| `SKILL.md#23-see-also` | See Also | unclassified | none | — |
| `SKILL.md#24-common-rationalizations` | Common Rationalizations | unclassified | none | — |
| `SKILL.md#25-red-flags` | Red Flags | unclassified | none | — |
| `SKILL.md#26-verification` | Verification | unclassified | none | — |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:37+00:00
