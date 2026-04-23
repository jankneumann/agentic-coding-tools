# Skillify Promotion — Spec Delta

## ADDED Requirements

### Requirement: Failure-to-skill scaffolding command

The system SHALL provide a `/skillify` skill that scaffolds a new skill directory and a draft OpenSpec change in one operation.

#### Scenario: Default invocation scaffolds skill in current repo

- **WHEN** a user runs `/skillify <skill-name>` from inside `agentic-coding-tools`
- **THEN** the skill MUST infer `--target-repo coding-tools` from `git remote get-url origin`
- **AND** create `skills/<skill-name>/SKILL.md` with valid frontmatter (`name`, `description`, `category`, `tags`, `triggers`)
- **AND** create empty placeholder directories `skills/<skill-name>/scripts/` and `skills/tests/<skill-name>/`
- **AND** create `openspec/changes/skillify-<skill-name>/proposal.md` as a stub

#### Scenario: Explicit target-repo override

- **WHEN** a user runs `/skillify <skill-name> --target-repo content-analyzer`
- **THEN** the skill MUST verify the current working directory's git remote matches `agentic-content-analyzer`
- **AND** if it does not match, exit with status 1 and print a message instructing the user to cd into the target repo first

#### Scenario: Invalid skill name rejected

- **WHEN** a user runs `/skillify <name>` and `<name>` is not valid kebab-case (e.g. contains uppercase, underscores, or spaces)
- **THEN** the skill MUST exit with status 1
- **AND** print the validation rule that was violated

#### Scenario: Existing skill name rejected

- **WHEN** a user runs `/skillify <name>` and `skills/<name>/` already exists
- **THEN** the skill MUST exit with status 1
- **AND** print a message naming the existing path

### Requirement: Scaffolded SKILL.md is valid

The scaffolded `SKILL.md` SHALL be parseable and conformant to the project's skill frontmatter conventions.

#### Scenario: Frontmatter parses as YAML

- **WHEN** `/skillify <name>` completes successfully
- **THEN** the generated `skills/<name>/SKILL.md` MUST begin with a valid YAML frontmatter block
- **AND** the frontmatter MUST include the keys `name`, `description`, `category`, `tags`, and `triggers`
- **AND** `name` MUST equal `<name>`
- **AND** `triggers` MUST be a non-empty list (at minimum, the skill name itself)

### Requirement: Scaffolded OpenSpec change is a stub

The scaffolded OpenSpec change SHALL be discoverable by `openspec list` and SHALL not pass `openspec validate` until the user fills it in.

#### Scenario: openspec list shows the new change

- **WHEN** `/skillify <name>` completes
- **AND** the user runs `openspec list`
- **THEN** the listing MUST include `skillify-<name>` with task count `0/N` (where N is the stub task count)

#### Scenario: Stub proposal directs user to next step

- **WHEN** the user reads the generated `proposal.md`
- **THEN** the document MUST include a "Next Steps" section instructing the user to run `/plan-feature skillify-<name>` to formalize the proposal before implementation

### Requirement: Skillify does not auto-commit

The `/skillify` skill SHALL leave all generated files staged but uncommitted, so the user can review and adjust before committing.

#### Scenario: Files staged after skillify

- **WHEN** `/skillify <name>` completes
- **AND** the user runs `git status`
- **THEN** the output MUST list the generated `skills/<name>/SKILL.md`, scripts/tests placeholders, and `openspec/changes/skillify-<name>/` files in the staged-changes section

#### Scenario: No commit created automatically

- **WHEN** `/skillify <name>` completes
- **AND** the user runs `git log -1 --oneline`
- **THEN** the most recent commit SHA MUST be unchanged from before `/skillify` was run
