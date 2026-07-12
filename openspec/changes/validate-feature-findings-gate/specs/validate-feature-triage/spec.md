## ADDED Requirements

### Requirement: Interactive per-finding triage

The system SHALL accept a `--triage` flag that walks findings whose `fixability`
is `escalate` one at a time and collects an `approve` / `fix` / `skip`
`triage_state` for each, writing the chosen `triage_state` back to the findings
file. Triage SHALL write only the new `triage_state` field and SHALL NOT alter
the existing `disposition` field.

#### Scenario: Operator triages an escalated finding

- **WHEN** `validate-feature <change-id> --triage` runs with an untriaged
  `escalate` finding
- **THEN** the system SHALL present the finding and prompt for
  `approve` / `fix` / `skip`
- **AND** the chosen `triage_state` SHALL be written back to the finding in
  `validation-findings.json`

#### Scenario: Triage surface adapts to harness

- **WHEN** triage runs inside the agent harness
- **THEN** it SHALL collect the `triage_state` via `AskUserQuestion`
- **WHEN** triage runs from the CLI
- **THEN** it SHALL collect the `triage_state` via an interactive prompt loop
- **AND** both surfaces SHALL write identical `triage_state` fields

### Requirement: Non-interactive auto mode

The system SHALL accept a `-y` / `--auto` flag that applies each finding's default
`triage_state` without prompting, for headless and CI use. The default
`triage_state` SHALL be deterministic: a finding with `fixability: auto-fix` that
was already resolved by the auto-fix step defaults to `fix`, and every remaining
`escalate` finding defaults to `skip` (never `approve`, so `--auto` never silently
accepts an intent-touching issue). The chosen default SHALL be recorded on each
finding.

#### Scenario: Auto mode applies deterministic defaults headlessly

- **WHEN** `validate-feature <change-id> --triage --auto` runs
- **THEN** each resolved `auto-fix` finding SHALL be set to `triage_state: fix` and
  each unresolved `escalate` finding SHALL be set to `triage_state: skip`
- **AND** no finding SHALL be defaulted to `approve`
- **AND** the report SHALL record that triage states were applied automatically

### Requirement: Resumable curated state

A subsequent `validate-feature` run SHALL resume from the `triage_state` values
recorded in the findings file, so previously-skipped or approved findings are not
re-prompted.

#### Scenario: Re-run honors prior triage state

- **WHEN** `validate-feature` re-runs after a triage session
- **THEN** findings already marked `triage_state` `skip` or `approve` SHALL NOT be
  re-presented
- **AND** only new or still-untriaged findings SHALL require triage
