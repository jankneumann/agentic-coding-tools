## ADDED Requirements

### Requirement: Phases emit structured findings

Every `validate-feature` phase SHALL emit each issue it detects as a finding
record appended to the `findings[]` array of a per-run validation-findings file at
`openspec/changes/<change-id>/validation-findings.json`, in addition to any
human-readable output. The validation finding record is defined by the new
`validation-findings.schema.json` and borrows the familiar field names from a
review finding (`id`, `type`, `criticality`, `description`, originating `phase`,
affected file/endpoint) plus the optional `fixability` / `triage_state` fields. It
SHALL NOT require the review schema's review-only fields (`disposition`, `axis`,
`severity`); a validation finding is its own record type, not an instance of
`review-findings.schema.json`, whose `review_type` enum (`plan` /
`implementation`) does not describe a validation run and which has no phase-status
container. Reusing the field *names* keeps tooling familiar without coupling the
two schemas' required-field sets.

#### Scenario: Phase failure produces a finding record

- **WHEN** a `validate-feature` phase (e.g. `smoke`, `security`, `architecture`)
  detects an issue
- **THEN** the phase SHALL append a finding to the `findings[]` array of
  `validation-findings.json` that validates against `validation-findings.schema.json`
- **AND** the finding SHALL identify the originating phase, the affected file or
  endpoint, and a criticality

#### Scenario: Clean phase produces no findings

- **WHEN** a phase passes with no issues
- **THEN** the phase SHALL add no findings for that run
- **AND** the phase SHALL record an explicit `pass` status (see "Phases record
  explicit execution status") so a pass is asserted from a positive record, never
  merely inferred from the absence of findings

### Requirement: Phases record explicit execution status

Every `validate-feature` phase SHALL have exactly **one** current status entry in
`phase_statuses[]` — its `final_status` of `pass`, `fail`, `skip`, `not-run`, or
`error`, plus a short reason — even across retries and auto-fix re-runs, which
SHALL update that single entry to the outcome of the latest attempt (an optional
ordered `attempts[]` history MAY record prior outcomes but SHALL NOT be consulted
for the phase result). A phase result SHALL be derived only from its `final_status`;
the absence of findings for a phase SHALL NOT by itself be treated as a pass, so a
skipped, not-run, or crashed-before-emit phase is never misreported as passing.

#### Scenario: Skipped phase is distinguishable from a pass

- **WHEN** a phase is skipped (e.g. no live services, no applicable tests)
- **THEN** the phase SHALL record a `skip` `final_status` with a reason
- **AND** the report SHALL show the phase as `skip`, not `pass`

#### Scenario: Auto-fixed phase resolves to its latest outcome

- **WHEN** a phase records `fail`, an `auto-fix` is applied, and the re-run passes
- **THEN** the phase's single `final_status` SHALL be updated to `pass`
- **AND** the report and gate SHALL read `pass` (the latest outcome), regardless of
  any earlier `fail` retained in `attempts[]`

#### Scenario: Phase that crashes before emitting is not a pass

- **WHEN** a phase terminates abnormally before it can emit findings
- **THEN** its status SHALL be recorded as `error` (or left `not-run` if it never
  started)
- **AND** the report SHALL NOT assert a pass for that phase

### Requirement: Findings carry a fixability tier

Each validation finding SHALL carry an optional `fixability` field of `auto-fix`
or `escalate` (defined on the validation finding record, not on the review
schema's `disposition`). `auto-fix` SHALL be assigned only to mechanical,
behavior-preserving issues; any issue that could touch program intent or behavior
SHALL be `escalate`. When the
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

### Requirement: Findings have a stable identity

Each validation finding SHALL carry a deterministic `fingerprint` derived from its
stable attributes (originating `phase`, `type`, normalized location, and a
normalized message/check key) — not from its array position or the per-run integer
`id`. Because `validation-findings.json` is regenerated each run, a new run SHALL
merge prior `triage_state` (and any waiver) onto findings by matching
`fingerprint`, so curated state survives re-ordering and is never attached to the
wrong finding.

#### Scenario: Triage state re-attaches after re-ordering

- **WHEN** a re-run regenerates `validation-findings.json` and the findings appear
  in a different order
- **THEN** each finding's prior `triage_state` SHALL be re-attached by matching
  `fingerprint`
- **AND** a finding whose `fingerprint` no longer appears SHALL be treated as
  resolved/disappeared, while a new `fingerprint` SHALL start untriaged

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

### Requirement: New self-contained validation-findings schema; review schema untouched

This change SHALL add a new `openspec/schemas/validation-findings.schema.json` that
fully describes the validation artifact: an envelope (`schema_version`, `change_id`,
the validated commit), a `phase_statuses[]` array (each `{ phase, status, reason }`),
and a `findings[]` array whose item is a self-contained validation finding record
(`id`, `type`, `criticality`, `description`, `phase`, affected file/endpoint, and
the optional `fixability` and `triage_state`). This change SHALL NOT modify
`review-findings.schema.json` at all — it does not add `fixability` / `triage_state`
to it, does not touch its required `disposition` field (enum `fix` / `regenerate` /
`accept` / `escalate`), and does not add a `validation` value to its `review_type`
enum — so the parallel-review pipeline and its consumers are wholly unaffected.

#### Scenario: Review schema and its consumers are unaffected

- **WHEN** the change is applied
- **THEN** `review-findings.schema.json` (its `disposition`, `axis`, `severity`
  required fields and its `review_type` enum) SHALL be byte-for-byte unchanged
- **AND** existing consumers (architecture linters, consensus synthesizer) SHALL
  need no modification

#### Scenario: Validation-findings file validates against its own schema

- **WHEN** a complete `validation-findings.json` (envelope + `phase_statuses[]` +
  `findings[]`) is validated
- **THEN** it SHALL validate against `validation-findings.schema.json`
- **AND** it SHALL NOT be required to satisfy `review-findings.schema.json`

#### Scenario: Omitted optional fields take their defaults

- **WHEN** a validation finding omits `fixability`
- **THEN** it SHALL be treated as `escalate`
- **AND** a finding that omits `triage_state` SHALL be treated as un-triaged
