## ADDED Requirements

### Requirement: Product-Management Skill Suite

The skills system SHALL provide a product-discovery layer of twelve new skills under
`skills/<name>/`, each ported from the public `phuryn/pm-skills` repository and adapted to our
frontmatter schema and OpenSpec/agent-coordination context. Each new skill SHALL be installable via
the existing `skills/install.sh` auto-discovery mechanism (any directory containing `SKILL.md` is
installed).

The twelve new skills, their seam, and their `user_invocable` assignments SHALL be:

| Seam | Skill | `user_invocable` |
|---|---|---|
| 1 | `create-prd` | `true` |
| 1 | `opportunity-solution-tree` | `true` |
| 2 | `prioritize-features` | `true` |
| 2 | `identify-assumptions` | `true` |
| 3 | `strategy-red-team` | `true` |
| 3 | `pre-mortem` | `true` |
| 4 | `user-stories` | `true` |
| 4 | `test-scenarios` | `true` |
| 5 | `intended-vs-implemented` | `true` |
| 5 | `shipping-artifacts` | `false` |
| 6 | `outcome-roadmap` | `true` |
| 6 | `brainstorm-okrs` | `true` |

Each new skill SHALL adapt the source skill's substantive content and SHALL express its primary
output in an artifact an existing skill consumes (for example: `create-prd` output SHALL be a valid
`proposal.md`; `user-stories` / `test-scenarios` output SHALL include OpenSpec WHEN/THEN scenario
blocks). The minimal `name + description` frontmatter form used by the source repository SHALL NOT
be adopted.

#### Scenario: New product-management skill is auto-discovered

**WHEN** `skills/install.sh` runs against a target directory
**THEN** each of the twelve new skills SHALL be installed under `.claude/skills/<name>/` and
`.agents/skills/<name>/`
**AND** the installed `SKILL.md` SHALL contain the adapted product-management content
**AND** the installed `SKILL.md` SHALL contain at least one OpenSpec/agent-coordination example
tying the skill's output to an existing consuming skill

#### Scenario: user_invocable assignment is honored by skill discovery

**WHEN** an agent enumerates user-invocable skills
**THEN** the eleven skills assigned `user_invocable: true` SHALL appear in the slash-command palette
**AND** `shipping-artifacts` (`user_invocable: false`) SHALL NOT appear in the slash-command palette
**AND** `shipping-artifacts` SHALL still be loadable by other skills via the `Skill` tool or direct
file read

#### Scenario: Frontmatter schema preserved

**WHEN** any new product-management skill is loaded
**THEN** its YAML frontmatter SHALL conform to the existing schema: required `name`, `description`,
`category`, `tags`, `triggers`; optional `user_invocable`, `requires`, `related`
**AND** the `related:` key SHALL name the skill's seam partner and at least one consuming skill

---

### Requirement: Tail Block Convention Applies to New User-Invocable PM Skills

Every new product-management skill where `user_invocable: true` SHALL end its `SKILL.md` with the
three tail-block sections in the established order (`## Common Rationalizations`, `## Red Flags`,
`## Verification`), consistent with the repo-wide tail-block convention. `shipping-artifacts`
(`user_invocable: false`) SHALL be exempt.

#### Scenario: New user-invocable PM skill ships the tail block

**WHEN** any of the eleven user-invocable new skills is read
**THEN** its `SKILL.md` SHALL contain `## Common Rationalizations`, `## Red Flags`, and
`## Verification` in that exact order
**AND** the `## Common Rationalizations` table SHALL contain at least three rows
**AND** the `## Red Flags` list SHALL contain at least three bullets
**AND** the `## Verification` checklist SHALL contain at least three numbered items

#### Scenario: Infrastructure PM skill is exempt

**WHEN** `shipping-artifacts` (`user_invocable: false`) is read
**THEN** the tail-block sections MAY be omitted without violating the convention

---

### Requirement: Prioritization Frameworks Reference Document

The shared `skills/references/` library SHALL gain a `prioritization-frameworks.md` document
cataloguing standard prioritization methods (at minimum RICE, WSJF, Kano, and MoSCoW) with a
one-line "use when" for each. The document SHALL NOT be a skill (no `SKILL.md`, no palette entry)
and SHALL be cited by `prioritize-features` and `identify-assumptions`.

#### Scenario: Reference installed alongside skills

**WHEN** `skills/install.sh` runs in `--mode rsync`
**THEN** `skills/references/prioritization-frameworks.md` SHALL be synced to
`.claude/skills/references/` and `.agents/skills/references/`

#### Scenario: Reference is cited, not discovered as a skill

**WHEN** `skills/install.sh` enumerates skill directories
**THEN** `prioritization-frameworks.md` SHALL NOT be treated as a skill
**AND** the `prioritize-features` `SKILL.md` citation of `references/prioritization-frameworks.md`
SHALL resolve at the installed path

---

### Requirement: Content-Invariant Test Coverage for PM Skills

Each new product-management skill SHALL ship a test file
`skills/tests/<skill-name>/test_skill_md.py` invoking the existing shared assertions from
`skills/tests/_shared/conftest.py` (`assert_frontmatter_parses`, `assert_required_keys_present`,
`assert_references_resolve`, `assert_related_resolve`, and — for user-invocable skills —
`assert_tail_block_present`). `skills/pyproject.toml`'s `[tool.pytest.ini_options]` `testpaths`
SHALL list every new test directory.

#### Scenario: New skill test directories are collected

**WHEN** `cd skills && uv run pytest --collect-only` runs
**THEN** all twelve new skill test directories SHALL be collected

#### Scenario: Missing tail block is caught for a user-invocable PM skill

**WHEN** a user-invocable new skill's `SKILL.md` is missing any tail-block section
**AND** the test suite runs
**THEN** `assert_tail_block_present` SHALL fail with a message naming the missing section

#### Scenario: Unresolved reference or related target is caught

**WHEN** a new skill cites `references/prioritization-frameworks.md` or declares a `related:` target
that does not exist
**AND** the test suite runs
**THEN** `assert_references_resolve` or `assert_related_resolve` SHALL fail with a message naming the
unresolved target
