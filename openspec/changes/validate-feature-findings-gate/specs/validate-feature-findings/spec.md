## ADDED Requirements

### Requirement: Phases emit structured findings

Every `validate-feature` phase SHALL emit each issue it detects as a record
conforming to `openspec/schemas/review-findings.schema.json`, written to a
per-run findings file at `openspec/changes/<change-id>/validation-findings.json`,
in addition to any human-readable output.

#### Scenario: Phase failure produces a finding record

- **WHEN** a `validate-feature` phase (e.g. `smoke`, `security`, `architecture`)
  detects an issue
- **THEN** the phase SHALL append a finding to `validation-findings.json` that
  validates against `review-findings.schema.json`
- **AND** the finding SHALL identify the originating phase, the affected file or
  endpoint, and a severity

#### Scenario: Clean phase produces no findings

- **WHEN** a phase passes with no issues
- **THEN** the phase SHALL add no findings for that run
- **AND** the absence of findings for a phase SHALL be reported as a pass

### Requirement: Findings carry an auto-fix vs escalate disposition

Each finding SHALL carry a `disposition` field of `auto-fix` or `escalate`.
`auto-fix` SHALL be assigned only to mechanical, behavior-preserving issues; any
issue that could touch program intent or behavior SHALL be `escalate`. When the
classification is uncertain, the disposition SHALL default to `escalate`.

#### Scenario: Mechanical issue classified auto-fix

- **WHEN** a finding describes a mechanical, behavior-preserving issue (e.g.
  formatting, import order, naming-convention violation)
- **THEN** its `disposition` SHALL be `auto-fix`

#### Scenario: Intent-touching issue classified escalate

- **WHEN** a finding could change behavior, API surface, or program intent
- **THEN** its `disposition` SHALL be `escalate`

#### Scenario: Uncertain classification defaults to escalate

- **WHEN** a finding's disposition cannot be determined with confidence
- **THEN** its `disposition` SHALL default to `escalate`

### Requirement: Auto-fix triage step

The system SHALL provide a triage step that applies `auto-fix` findings by
delegating to the existing `simplify` / `fix-scrub` low-risk fixers, re-runs the
affected phase, and reverts the fix if the re-run regresses.

#### Scenario: Auto-fix applied and phase re-validated

- **WHEN** the triage step processes an `auto-fix` finding
- **THEN** it SHALL apply the fix via the `simplify` / `fix-scrub` low-risk fixers
- **AND** it SHALL re-run the originating phase
- **AND** on a passing re-run it SHALL mark the finding resolved

#### Scenario: Regressing auto-fix reverted

- **WHEN** an applied `auto-fix` causes the re-run of its phase to fail
- **THEN** the triage step SHALL revert the fix
- **AND** SHALL re-classify the finding as `escalate`

### Requirement: Report rendered from findings file

The `validate-feature` markdown report (`validation-report.md`) SHALL be rendered
from `validation-findings.json` so that the human-readable report and the
machine-readable findings share a single source of truth.

#### Scenario: Report reflects findings file

- **WHEN** the validation report is generated
- **THEN** every phase result and finding in the report SHALL derive from
  `validation-findings.json`
- **AND** the report SHALL not assert a pass for any phase that has an unresolved
  finding in the findings file

### Requirement: Backward-compatible schema extension

The `disposition` field SHALL be added to `review-findings.schema.json` as an
optional field with a default of `escalate`, leaving all existing required fields
and consumers unchanged.

#### Scenario: Existing consumer reads extended findings

- **WHEN** an existing consumer (architecture linters, consensus synthesizer)
  reads a findings file that includes the `disposition` field
- **THEN** the consumer SHALL continue to function without modification
- **AND** a finding that omits `disposition` SHALL be treated as `escalate`
