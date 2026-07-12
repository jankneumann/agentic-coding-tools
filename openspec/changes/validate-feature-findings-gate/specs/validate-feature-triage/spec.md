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

### Requirement: Triage state resolution semantics

Each `triage_state` value SHALL have explicit resolution semantics so that
suppressing a re-prompt never silently clears a finding. `triage_state: fix` (the
finding was fixed) and `triage_state: approve` (an explicit, recorded human
waiver) SHALL mark a finding **resolved**. `triage_state: skip` SHALL leave a
finding **unresolved**: it SHALL continue to count as an unresolved finding for
report and gate purposes (so it keeps a phase failing), even though a later triage
run does not re-prompt it. `--auto` therefore never silently passes a critical
finding, because its default of `skip` for `escalate` findings keeps them
unresolved.

#### Scenario: Skip suppresses the prompt but not the failure

- **WHEN** a finding is marked `triage_state: skip`
- **THEN** it SHALL still be reported as unresolved and SHALL keep its phase and
  any gate that includes it failing
- **AND** a subsequent triage run SHALL NOT re-present it

#### Scenario: Only fix or approve resolves a finding

- **WHEN** a finding is marked `triage_state: fix` or `triage_state: approve`
- **THEN** it SHALL be treated as resolved for report and gate purposes
- **AND** an `approve` SHALL be recorded as an explicit waiver in the findings file

### Requirement: Resumable curated state

A subsequent `validate-feature` run SHALL resume from the `triage_state` values
recorded in the findings file, merging them onto the regenerated findings by
`fingerprint` (see "Findings have a stable identity"), so previously-skipped or
approved findings are not re-prompted even if their order changes.

#### Scenario: Re-run honors prior triage state

- **WHEN** `validate-feature` re-runs after a triage session
- **THEN** findings whose `fingerprint` was already marked `triage_state` `skip` or
  `approve` SHALL NOT be re-presented
- **AND** only findings with a new or still-untriaged `fingerprint` SHALL require
  triage
