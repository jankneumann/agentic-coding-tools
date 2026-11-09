# Skill audit: api-and-interface-design

- convention: rightsizing
- evidence: unavailable (unauthorized)
- evidence_window_days: 30
- context_cost: n/a (ri-04 doctor baseline not available)
- model_calls: 1 (batch of 8 undecided section(s))
- generated_at: 2026-09-16T11:40:46+00:00

> skill-audit: api-and-interface-design: model output invalid or unavailable; 8 section(s) labelled unclassified

## Layer histogram

| Layer | Sections |
|---|---|
| contract | 13 |
| constraint | 0 |
| procedure | 0 |
| teaching | 0 |
| unclassified | 8 |

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
| 1 | F001 | contract_unpinned | contract | `SKILL.md#05-1-contract-first` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 2 | F002 | contract_unpinned | contract | `SKILL.md#06-2-consistent-error-semantics` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 3 | F003 | contract_unpinned | contract | `SKILL.md#07-3-validate-at-boundaries` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 4 | F004 | contract_unpinned | contract | `SKILL.md#08-4-prefer-addition-over-modification` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 5 | F005 | contract_unpinned | contract | `SKILL.md#10-resource-design` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 6 | F006 | contract_unpinned | contract | `SKILL.md#11-pagination` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 7 | F007 | contract_unpinned | contract | `SKILL.md#12-filtering` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 8 | F008 | contract_unpinned | contract | `SKILL.md#13-partial-updates-patch` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 9 | F009 | contract_unpinned | contract | `SKILL.md#14-discriminated-unions-for-variants` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 10 | F010 | contract_unpinned | contract | `SKILL.md#15-branded-nominal-types-for-ids` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 11 | F011 | contract_unpinned | contract | `SKILL.md#16-immutable-value-objects-frozen-dataclass` | add_probe | — | No test cites this contract section; drift would go unnoticed. |
| 12 | F012 | convention_drift | contract | `SKILL.md` | move_to_reference | rule `max_lines` | SKILL.md has 531 lines; the rightsizing cap is 500 |

## Proposed lean SKILL.md outline

Keep in SKILL.md (contract and constraint sections, in document order):

- frontmatter (`contract`)
- 1. Contract First (`contract`)
- 2. Consistent Error Semantics (`contract`)
- 3. Validate at Boundaries (`contract`)
- 4. Prefer Addition Over Modification (`contract`)
- Resource Design (`contract`)
- Pagination (`contract`)
- Filtering (`contract`)
- Partial Updates (PATCH) (`contract`)
- Discriminated Unions for Variants (`contract`)
- Branded / Nominal Types for IDs (`contract`)
- Immutable Value Objects (frozen dataclasses) (`contract`)
- Input/Output Separation (`contract`)

## Proposed references/procedure.md outline

No procedure sections; nothing to extract.

## Layer table

| Section | Heading | Layer | Decided by | Rule |
|---|---|---|---|---|
| `SKILL.md#00-frontmatter` | frontmatter | contract | pre-pass | frontmatter |
| `SKILL.md#01-overview` | Overview | unclassified | none | — |
| `SKILL.md#02-when-to-use` | When to Use | unclassified | none | — |
| `SKILL.md#03-hyrum-s-law` | Hyrum's Law | unclassified | none | — |
| `SKILL.md#04-the-one-version-rule` | The One-Version Rule | unclassified | none | — |
| `SKILL.md#05-1-contract-first` | 1. Contract First | contract | pre-pass | fenced_command |
| `SKILL.md#06-2-consistent-error-semantics` | 2. Consistent Error Semantics | contract | pre-pass | fenced_command |
| `SKILL.md#07-3-validate-at-boundaries` | 3. Validate at Boundaries | contract | pre-pass | fenced_command |
| `SKILL.md#08-4-prefer-addition-over-modification` | 4. Prefer Addition Over Modification | contract | pre-pass | fenced_command |
| `SKILL.md#09-5-predictable-naming` | 5. Predictable Naming | unclassified | none | — |
| `SKILL.md#10-resource-design` | Resource Design | contract | pre-pass | fenced_command |
| `SKILL.md#11-pagination` | Pagination | contract | pre-pass | fenced_command |
| `SKILL.md#12-filtering` | Filtering | contract | pre-pass | fenced_command |
| `SKILL.md#13-partial-updates-patch` | Partial Updates (PATCH) | contract | pre-pass | fenced_command |
| `SKILL.md#14-discriminated-unions-for-variants` | Discriminated Unions for Variants | contract | pre-pass | fenced_command |
| `SKILL.md#15-branded-nominal-types-for-ids` | Branded / Nominal Types for IDs | contract | pre-pass | fenced_command |
| `SKILL.md#16-immutable-value-objects-frozen-dataclass` | Immutable Value Objects (frozen dataclasses) | contract | pre-pass | fenced_command |
| `SKILL.md#17-input-output-separation` | Input/Output Separation | contract | pre-pass | fenced_command |
| `SKILL.md#18-common-rationalizations` | Common Rationalizations | unclassified | none | — |
| `SKILL.md#19-red-flags` | Red Flags | unclassified | none | — |
| `SKILL.md#20-verification` | Verification | unclassified | none | — |

## Freshness stamp

- archetypes_sha256: 5cfdd2f5e34d7ae83201695604a0382adcd9e2a2fe003b854959112e4800ed7a
- reviewed_dates: 2026-08-16
- evidence_window_days: 30
- generated_at: 2026-09-16T11:40:46+00:00
