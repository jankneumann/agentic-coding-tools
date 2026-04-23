# Resolver Audit — Spec Delta

## ADDED Requirements

### Requirement: Dark-skill detection

The system SHALL detect skills that have an empty or missing `triggers:` list in their SKILL.md frontmatter.

#### Scenario: Skill with empty triggers list reported as dark

- **WHEN** the resolver audit runs
- **AND** any `skills/*/SKILL.md` has frontmatter where `triggers:` is missing, null, or an empty list
- **THEN** the audit MUST report a finding of type `dark_skill` for that skill
- **AND** the finding MUST include the skill's directory name and the file path

#### Scenario: Skill with non-empty triggers passes

- **WHEN** the resolver audit runs
- **AND** every `skills/*/SKILL.md` has at least one entry in `triggers:`
- **THEN** no `dark_skill` findings MUST be reported

### Requirement: Trigger-overlap detection

The system SHALL detect when two or more skills declare triggers that match the same canonical user intent.

#### Scenario: Identical triggers across skills

- **WHEN** the resolver audit runs
- **AND** two or more skills have a trigger string that matches case-insensitively after whitespace normalization
- **THEN** the audit MUST report a finding of type `trigger_overlap` listing all colliding skills and the shared trigger phrase

#### Scenario: Distinct triggers do not collide

- **WHEN** every skill's triggers are distinct (after case + whitespace normalization)
- **THEN** no `trigger_overlap` findings MUST be reported

#### Scenario: Substring overlap reported as warning, not error

- **WHEN** one skill's trigger is a substring of another skill's trigger (e.g. "calendar" vs "calendar recall")
- **THEN** the audit MUST report a finding of type `trigger_overlap` with severity `warning` (not `error`)
- **AND** the finding MUST suggest disambiguation in the longer trigger

### Requirement: Missing-script detection

The system SHALL detect when a SKILL.md references a script path under its own `scripts/` directory that does not exist on disk.

#### Scenario: Referenced script exists

- **WHEN** the resolver audit runs
- **AND** every `scripts/*.{py,sh,mjs,js,ts}` path mentioned in any SKILL.md exists on disk under that skill's directory
- **THEN** no `missing_script` findings MUST be reported

#### Scenario: Referenced script missing

- **WHEN** a SKILL.md references `scripts/foo.py` but the file does not exist
- **THEN** the audit MUST report a `missing_script` finding identifying the SKILL.md, the missing path, and the line number where it was referenced

### Requirement: JSON output mode

The audit script SHALL support a `--json` flag that emits machine-readable output for CI integration.

#### Scenario: JSON mode emits valid JSON

- **WHEN** `python3 skills/resolver-audit/scripts/resolver_audit.py --json` runs
- **THEN** stdout MUST be a single JSON object with keys `findings` (array) and `summary` (object with counts per type)
- **AND** stderr MUST be empty on success

#### Scenario: JSON mode includes finding metadata

- **WHEN** the audit reports any findings in `--json` mode
- **THEN** each finding object MUST include `type`, `severity`, `skill_name`, `path`, and `message` keys

### Requirement: Fail-on-findings exit code

The audit script SHALL support a `--fail-on-findings` flag that causes non-zero exit when any error-severity finding is present.

#### Scenario: Findings present, fail flag set, error exit

- **WHEN** `resolver_audit.py --fail-on-findings` runs and any error-severity finding exists
- **THEN** the script MUST exit with status 1

#### Scenario: Only warnings present, fail flag set, success exit

- **WHEN** `resolver_audit.py --fail-on-findings` runs and only warning-severity findings exist (no errors)
- **THEN** the script MUST exit with status 0

#### Scenario: No findings, fail flag set, success exit

- **WHEN** `resolver_audit.py --fail-on-findings` runs and no findings exist
- **THEN** the script MUST exit with status 0

### Requirement: validate-feature integration

The `/validate-feature` skill SHALL accept a `--phase resolver` selector that runs the resolver audit and reports findings as part of the validation report.

#### Scenario: Resolver phase runs audit

- **WHEN** `/validate-feature --phase resolver` is invoked
- **THEN** the validation MUST run `resolver_audit.py --json --fail-on-findings`
- **AND** the validation report MUST include the parsed JSON findings under a `resolver` section

#### Scenario: Resolver phase fails validation on errors

- **WHEN** `/validate-feature --phase resolver` runs and the audit returns non-zero
- **THEN** the validate-feature exit MUST be non-zero
- **AND** the failure summary MUST list the resolver findings
