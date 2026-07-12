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
- **AND** the phase SHALL record an explicit `pass` status (see "Phases record
  explicit execution status") so a pass is asserted from a positive record, never
  merely inferred from the absence of findings

### Requirement: Phases record explicit execution status

Every `validate-feature` phase SHALL write an explicit per-phase execution-status
record to `validation-findings.json` with a status of `pass`, `fail`, `skip`,
`not-run`, or `error`, plus a short reason. A phase result SHALL be derived only
from its status record; the absence of findings for a phase SHALL NOT by itself
be treated as a pass, so a skipped, not-run, or crashed-before-emit phase is
never misreported as passing.

#### Scenario: Skipped phase is distinguishable from a pass

- **WHEN** a phase is skipped (e.g. no live services, no applicable tests)
- **THEN** the phase SHALL record a `skip` status with a reason
- **AND** the report SHALL show the phase as `skip`, not `pass`

#### Scenario: Phase that crashes before emitting is not a pass

- **WHEN** a phase terminates abnormally before it can emit findings
- **THEN** its status SHALL be recorded as `error` (or left `not-run` if it never
  started)
- **AND** the report SHALL NOT assert a pass for that phase

### Requirement: Findings carry a fixability tier

Each finding SHALL carry an optional `fixability` field of `auto-fix` or
`escalate`, distinct from and additive to the existing `disposition` field.
`auto-fix` SHALL be assigned only to mechanical, behavior-preserving issues; any
issue that could touch program intent or behavior SHALL be `escalate`. When the
classification is uncertain, or when `fixability` is omitted, it SHALL default to
`escalate`.

#### Scenario: Mechanical issue classified auto-fix

- **WHEN** a finding describes a mechanical, behavior-preserving issue (e.g.
  formatting, import order, naming-convention violation)
- **THEN** its `fixability` SHALL be `auto-fix`

#### Scenario: Intent-touching issue classified escalate

- **WHEN** a finding could change behavior, API surface, or program intent
- **THEN** its `fixability` SHALL be `escalate`

#### Scenario: Uncertain classification defaults to escalate

- **WHEN** a finding's fixability cannot be determined with confidence
- **THEN** its `fixability` SHALL default to `escalate`

### Requirement: Auto-fix triage step

The system SHALL provide a triage step that applies findings whose `fixability`
is `auto-fix` by delegating to the existing `simplify` / `fix-scrub` low-risk
fixers, re-runs the affected phase, and reverts the fix if the re-run regresses.

#### Scenario: Auto-fix applied and phase re-validated

- **WHEN** the triage step processes a finding with `fixability: auto-fix`
- **THEN** it SHALL apply the fix via the `simplify` / `fix-scrub` low-risk fixers
- **AND** it SHALL re-run the originating phase
- **AND** on a passing re-run it SHALL mark the finding resolved

#### Scenario: Regressing auto-fix reverted

- **WHEN** an applied `auto-fix` causes the re-run of its phase to fail
- **THEN** the triage step SHALL revert the fix
- **AND** SHALL re-classify the finding's `fixability` as `escalate`

### Requirement: Report rendered from findings file

The `validate-feature` markdown report (`validation-report.md`) SHALL be rendered
from `validation-findings.json` so that the human-readable report and the
machine-readable findings share a single source of truth.

#### Scenario: Report reflects findings file

- **WHEN** the validation report is generated
- **THEN** every phase result and finding in the report SHALL derive from
  `validation-findings.json` — phase results from the per-phase status records and
  findings from the finding records
- **AND** the report SHALL not assert a pass for any phase whose status record is
  not `pass`, or that has an unresolved finding in the findings file

### Requirement: Additive schema extension preserves the disposition contract

This change SHALL NOT redefine or repurpose the existing required `disposition`
field in `review-findings.schema.json` (enum `fix` / `regenerate` / `accept` /
`escalate`), which the parallel-review pipeline consumes. Instead it SHALL add two
new **optional** fields — `fixability` (`auto-fix` / `escalate`, default
`escalate`) and `triage_state` (`approve` / `fix` / `skip`, unset until triaged) —
plus the per-phase status record, leaving `disposition` and all existing required
fields and consumers unchanged.

#### Scenario: Existing consumer reads extended findings

- **WHEN** an existing consumer (architecture linters, consensus synthesizer)
  reads a findings file that includes the new `fixability` / `triage_state` fields
- **THEN** the consumer SHALL continue to function without modification
- **AND** the existing `disposition` field SHALL retain its current enum and
  required status

#### Scenario: Omitted optional fields take their defaults

- **WHEN** a finding omits `fixability`
- **THEN** it SHALL be treated as `escalate`
- **AND** a finding that omits `triage_state` SHALL be treated as un-triaged
