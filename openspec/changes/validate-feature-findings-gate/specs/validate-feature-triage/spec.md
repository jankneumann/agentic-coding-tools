## ADDED Requirements

### Requirement: Interactive per-finding triage

The system SHALL accept a `--triage` flag that walks unresolved `escalate`
findings one at a time and collects an `approve` / `fix` / `skip` disposition for
each, writing the chosen disposition back to the findings file.

#### Scenario: Operator dispositions an escalated finding

- **WHEN** `validate-feature <change-id> --triage` runs with an unresolved
  `escalate` finding
- **THEN** the system SHALL present the finding and prompt for
  `approve` / `fix` / `skip`
- **AND** the chosen disposition SHALL be written back to the finding in
  `validation-findings.json`

#### Scenario: Triage surface adapts to harness

- **WHEN** triage runs inside the agent harness
- **THEN** it SHALL collect dispositions via `AskUserQuestion`
- **WHEN** triage runs from the CLI
- **THEN** it SHALL collect dispositions via an interactive prompt loop
- **AND** both surfaces SHALL write identical disposition fields

### Requirement: Non-interactive auto mode

The system SHALL accept a `-y` / `--auto` flag that applies each finding's
default disposition without prompting, for headless and CI use.

#### Scenario: Auto mode applies defaults headlessly

- **WHEN** `validate-feature <change-id> --triage --auto` runs
- **THEN** the system SHALL apply each finding's default disposition without
  prompting
- **AND** SHALL record in the report that dispositions were applied automatically

### Requirement: Resumable curated state

A subsequent `validate-feature` run SHALL resume from the dispositions recorded
in the findings file, so previously-skipped or approved findings are not
re-prompted.

#### Scenario: Re-run honors prior dispositions

- **WHEN** `validate-feature` re-runs after a triage session
- **THEN** findings already marked `skip` or `approve` SHALL NOT be re-presented
- **AND** only new or still-unresolved findings SHALL require triage
