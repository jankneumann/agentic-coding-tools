## ADDED Requirements

### Requirement: Engineering Methodology Skill Suite

The skills system SHALL provide a methodology layer of ten new skills under `skills/<name>/`, each ported from the public `addyosmani/agent-skills` repository and adapted to our frontmatter schema and Python-first stack. Each new skill SHALL be installable via the existing `skills/install.sh` auto-discovery mechanism (any directory containing `SKILL.md` is installed).

The ten new skills and their `user_invocable` assignments SHALL be:

| Skill | `user_invocable` |
|---|---|
| `test-driven-development` | `true` |
| `debugging-and-error-recovery` | `true` |
| `context-engineering` | `false` |
| `source-driven-development` | `false` |
| `performance-optimization` | `true` |
| `frontend-ui-engineering` | `true` |
| `api-and-interface-design` | `true` |
| `browser-testing-with-devtools` | `false` |
| `deprecation-and-migration` | `true` |
| `documentation-and-adrs` | `true` |

Each new skill SHALL preserve the original JS/TS examples from the source repository and SHALL include Python/pytest/FastAPI/pydantic equivalents alongside, never in place.

#### Scenario: New methodology skill is auto-discovered

**WHEN** `skills/install.sh` runs against a target directory
**THEN** each of the ten new skills SHALL be installed under `.claude/skills/<name>/` and `.agents/skills/<name>/`
**AND** the installed `SKILL.md` SHALL contain the original JS/TS examples
**AND** the installed `SKILL.md` SHALL contain at least one Python equivalent example per top-level technique section

#### Scenario: user_invocable assignment is honored by skill discovery

**WHEN** an agent enumerates user-invocable skills
**THEN** the seven skills assigned `user_invocable: true` SHALL appear in the slash-command palette
**AND** the three skills assigned `user_invocable: false` SHALL NOT appear in the slash-command palette
**AND** the three orchestrator-loaded skills SHALL still be loadable by other skills via the `Skill` tool or by direct file read

#### Scenario: Frontmatter schema preserved

**WHEN** any new methodology skill is loaded
**THEN** its YAML frontmatter SHALL conform to the existing schema: required `name`, `description`, `category`, `tags`, `triggers`; optional `user_invocable`, `requires`, `related`
**AND** the minimal `name + description` form used by the source repository SHALL NOT be adopted

---

### Requirement: Common Tail Block Convention for User-Invocable Skills

Every skill where `user_invocable: true` SHALL end its `SKILL.md` with three sub-sections in this exact order:

1. `## Common Rationalizations` — a Markdown table with two columns: "Rationalization" and "Why it's wrong"
2. `## Red Flags` — a bulleted list of observable signals indicating the skill is being violated
3. `## Verification` — a numbered checklist a reviewer or agent runs to confirm the skill was applied

The convention SHALL apply to:
- The three pilot skills: `simplify`, `bug-scrub`, `tech-debt-analysis`
- The ten new methodology skills (built in from day one)
- The eight ADAPT-target skills modified by this change: `implement-feature`, `parallel-review-plan`, `parallel-review-implementation`, `simplify` (already pilot), `security-review`, `plan-feature`, `cleanup-feature`, `merge-pull-requests`, `explore-feature`

Skills with `user_invocable: false` (infrastructure skills) SHALL be exempt.

A canonical template SHALL exist at `skills/references/skill-tail-template.md` for new skill authors to copy-paste.

#### Scenario: User-invocable skill ships tail block

**WHEN** any user-invocable skill is read
**THEN** its `SKILL.md` SHALL contain `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections
**AND** the three sections SHALL appear in that exact order
**AND** the `## Common Rationalizations` table SHALL contain at least three rows
**AND** the `## Red Flags` list SHALL contain at least three bullets
**AND** the `## Verification` checklist SHALL contain at least three numbered items

#### Scenario: Infrastructure skill is exempt

**WHEN** a skill with `user_invocable: false` is read
**THEN** the tail block sections MAY be omitted without violating the convention

#### Scenario: Tail-block template is available

**WHEN** an author copies `skills/references/skill-tail-template.md`
**THEN** the template SHALL contain placeholders for all three sections
**AND** the template SHALL include at least one filled-in example per section

---

### Requirement: Shared References Library

The skills system SHALL provide a shared `skills/references/` directory containing reusable Markdown documents that multiple skills cite. The directory SHALL ship with at least these four files at the time of this change:

- `security-checklist.md`
- `performance-checklist.md`
- `accessibility-checklist.md`
- `testing-patterns.md`

Plus the `skill-tail-template.md` introduced in the tail block requirement.

The `skills/references/` directory SHALL NOT contain a `SKILL.md` and SHALL NOT be treated as a skill by `install.sh`. It SHALL be installed alongside skills (rsynced into `.claude/skills/references/` and `.agents/skills/references/`) so that skills referencing relative paths like `references/security-checklist.md` resolve correctly at runtime.

#### Scenario: References library installed alongside skills

**WHEN** `skills/install.sh` runs in `--mode rsync`
**THEN** `skills/references/` SHALL be synced to `.claude/skills/references/` and `.agents/skills/references/`
**AND** the four checklist files SHALL exist at the destinations
**AND** `skill-tail-template.md` SHALL exist at the destinations

#### Scenario: References library is not auto-discovered as a skill

**WHEN** `skills/install.sh` enumerates skill directories
**THEN** `skills/references/` SHALL NOT be treated as a skill
**AND** the install.sh skill discovery loop SHALL skip the `references/` subdirectory

#### Scenario: Cross-skill reference resolves

**WHEN** a skill's `SKILL.md` cites `references/security-checklist.md`
**THEN** the file SHALL exist at the cited path relative to the installed skill's parent directory

---

### Requirement: `related:` Frontmatter Key

The skill frontmatter schema SHALL accept an optional `related:` key whose value is a YAML list of skill names. The key SHALL follow the same conventions as the existing `requires:` key and SHALL NOT change the meaning or behavior of any other frontmatter key.

The `related:` key SHALL declare cross-references for graph rendering and discovery; it SHALL NOT impose a hard dependency at runtime (unlike `requires:`).

`skills/install.sh` SHALL validate that every entry in any skill's `related:` list points to a skill directory that exists in `skills/`. If a `related:` entry references a non-existent skill, `install.sh` SHALL emit a warning but SHALL NOT fail the install.

#### Scenario: related key is parsed without breaking existing frontmatter

**WHEN** a skill's frontmatter declares `related: [test-driven-development, debugging-and-error-recovery]`
**THEN** the YAML SHALL parse without error
**AND** the existing keys (`name`, `description`, `category`, `tags`, `triggers`, `user_invocable`, `requires`) SHALL retain their meaning

#### Scenario: install.sh warns on unknown related target

**WHEN** a skill declares `related: [nonexistent-skill]`
**AND** `skills/install.sh` runs
**THEN** install.sh SHALL emit a warning naming the source skill and the unknown target
**AND** install.sh SHALL exit with status 0 (warning, not error)

#### Scenario: related key is optional

**WHEN** a skill omits the `related:` key
**THEN** install.sh SHALL not emit any warning
**AND** the skill SHALL install normally

---

### Requirement: Content-Invariant Test Framework for Skills

The skills test suite SHALL include a shared test framework at `skills/tests/_shared/conftest.py` that provides reusable assertions for skill quality invariants. The framework SHALL expose at minimum:

- `assert_frontmatter_parses(skill_path)` — YAML frontmatter loads without error
- `assert_required_keys_present(skill_path)` — `name`, `description`, `category`, `tags`, `triggers` are all present
- `assert_references_resolve(skill_path)` — every `references/<file>.md` cited in the SKILL.md body exists
- `assert_related_resolve(skill_path)` — every entry in the `related:` list points to an existing skill directory
- `assert_tail_block_present(skill_path)` — only when `user_invocable: true`, the three tail-block sections exist in correct order

Each new and adapted skill SHALL ship with a test file `skills/tests/<skill-name>/test_skill_md.py` invoking these assertions for that skill. `skills/pyproject.toml`'s `[tool.pytest.ini_options]` `testpaths` SHALL list every new test directory.

#### Scenario: Frontmatter parse failure is caught by tests

**WHEN** any new or adapted SKILL.md has malformed YAML frontmatter
**AND** `skills/.venv/bin/python -m pytest skills/tests/<skill-name>/` runs
**THEN** the test SHALL fail with a clear error message identifying the parse error

#### Scenario: Missing tail block is caught for user-invocable skills

**WHEN** a user-invocable skill's SKILL.md is missing any of the three tail-block sections
**AND** the test suite runs
**THEN** `assert_tail_block_present` SHALL fail with a message naming the missing section

#### Scenario: Reference cross-link rot is caught

**WHEN** a SKILL.md cites `references/security-checklist.md`
**AND** the file is removed or renamed
**AND** the test suite runs
**THEN** `assert_references_resolve` SHALL fail with a message naming the unresolved citation

#### Scenario: Test paths registered in pyproject

**WHEN** `cd skills && uv run pytest --collect-only` runs
**THEN** every new and adapted skill's test directory SHALL be collected
**AND** the collection SHALL include at least 18 new test directories (10 new skills + 8 ADAPT targets)

---

### Requirement: Pattern-Extraction Adaptations to Existing Skills

Eight existing skills SHALL be edited to incorporate specific patterns extracted from external methodology skills. Each ADAPT edit SHALL be combined in a single edit pass with the addition of the tail-block convention to that skill (avoiding double-touching files).

The eight adaptations SHALL be:

| Local skill modified | Patterns added |
|---|---|
| `implement-feature` | "Rules 0–5" framing; `NOTICED BUT NOT TOUCHING:` template injected into work-package execution prompts |
| `parallel-review-plan` and `parallel-review-implementation` | 5-axis review schema (Correctness / Readability / Architecture / Security / Performance); 5 severity prefixes (Critical / Nit / Optional / FYI / none) |
| `simplify` | Chesterton's Fence pre-check; "Rule of 500" trigger; pattern catalog |
| `security-review` | Three-tier boundary system; OWASP Top 10 prevention rules — added as a "preventive mode" alongside the existing scanner runner |
| `plan-feature` | XS/S/M/L/XL task sizing; "title contains 'and' → split signal"; explicit checkpoint cadence |
| `cleanup-feature` | 5%→25%→50%→100% staged rollout sequence; rollback triggers; pre-launch checklist phase |
| `merge-pull-requests` and `CLAUDE.md` | Save Point Pattern; Change Summary template (CHANGES MADE / DIDN'T TOUCH / CONCERNS) |
| `explore-feature` | "How Might We" reframing; 8 ideation lenses; explicit `NOT DOING:` list |

#### Scenario: implement-feature contains scope-discipline template

**WHEN** `implement-feature/SKILL.md` is read
**THEN** it SHALL contain a `NOTICED BUT NOT TOUCHING:` template
**AND** it SHALL contain a Rules 0–5 framing section

#### Scenario: simplify contains Chesterton's Fence pre-check

**WHEN** `simplify/SKILL.md` is read
**THEN** it SHALL contain a section titled "Chesterton's Fence" or referencing the pre-simplification questions
**AND** it SHALL contain a "Rule of 500" trigger description

#### Scenario: security-review contains preventive mode

**WHEN** `security-review/SKILL.md` is read
**THEN** it SHALL contain a section describing a preventive review mode using the three-tier boundary system
**AND** the existing scanner-runner mode SHALL remain documented

---

### Requirement: Review Findings Schema Extension

The schema at `skills/parallel-infrastructure/schemas/review-findings.schema.json` (or the equivalent path used by `parallel-review-plan` and `parallel-review-implementation`) SHALL be extended to encode the 5-axis review categorization and the 5 severity prefixes.

The schema SHALL add:

- An `axis` field on each finding with enum values: `correctness`, `readability`, `architecture`, `security`, `performance`
- A `severity` field on each finding with enum values: `critical`, `nit`, `optional`, `fyi`, `none`

Both fields SHALL be required for new findings. Findings produced before this change SHALL be migratable by setting `axis: "correctness"` and `severity: "fyi"` as defaults.

#### Scenario: New finding includes axis and severity

**WHEN** a parallel-review skill produces a finding
**THEN** the finding JSON SHALL include both `axis` and `severity` fields
**AND** the values SHALL match the schema enums

#### Scenario: Schema validation rejects missing fields

**WHEN** a finding without `axis` or `severity` is validated against the updated schema
**THEN** validation SHALL fail with a clear error identifying the missing field

#### Scenario: Existing schema fields preserved

**WHEN** the updated schema is loaded
**THEN** all pre-existing required fields SHALL remain required
**AND** all pre-existing enum values SHALL remain valid
