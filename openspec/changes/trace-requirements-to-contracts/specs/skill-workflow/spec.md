## MODIFIED Requirements

### Requirement: 3-Phase Incremental Generation

The `change-context.md` artifact SHALL be built incrementally across three
workflow phases, with the Contract Ref column generated from traceability
citations rather than mapped by hand.

#### Scenario: Phase 1 — Test plan (pre-implementation)
- **WHEN** the agent reads spec delta files before implementing tasks
- **THEN** the system SHALL populate Req ID, Spec Source, Description, Contract Ref, Design Decision, and Test(s) columns
- **AND** Contract Ref SHALL be generated from the traceability citations in the capability's contracts: for each requirement row, the contract documents whose operations cite that requirement's derived identifier, or `---` if no operation cites it
- **AND** the generator SHALL derive the ordinal Req ID and the traceability identifier from the same parse of the spec delta, joining rows to citations by parse position — it SHALL NOT re-match requirements to citations by name similarity
- **AND** Contract Ref SHALL NOT be populated by hand when the capability has any traced contract document
- **AND** Design Decision SHALL reference the decision from `design.md` (e.g., `D3`) that the requirement validates, or `---` if none applies
- **AND** Files Changed SHALL be set to `---`
- **AND** Evidence SHALL be set to `---`
- **AND** the agent SHALL write failing tests (RED) for each row in the matrix

#### Scenario: Phase 2 — Implementation
- **WHEN** the agent completes implementation tasks
- **THEN** the system SHALL update the Files Changed column with actual source files modified
- **AND** tests from Phase 1 SHALL now pass (GREEN)
- **AND** the Design Decision Trace Implementation column SHALL be populated if design.md exists

#### Scenario: Phase 3 — Validation evidence
- **WHEN** `/validate-feature` runs the spec compliance phase
- **THEN** the system SHALL fill the Evidence column for each requirement row
- **AND** evidence values SHALL be one of: `pass <short-SHA>`, `fail <short-SHA>`, `deferred <reason>`

## ADDED Requirements

### Requirement: Validation-Time Requirement Traceability Gate

The `/validate-feature` skill SHALL run the requirement-traceability gate
(`check_traceability.py`) in change scope during its spec-compliance phase, and
SHALL fail validation when the gate exits non-zero. Where the gate or
`openspec/contracts/` is absent, the skill SHALL print an explicit SKIP naming
what is missing and SHALL NOT fail validation.

The gate is the enforcement point for the requirement-to-contract edge: an
operation the change touches must cite the requirements it serves, and a
requirement the change adds must be cited or excluded, before the change
validates. Pre-existing violations the change did not create are reported by
the gate without failing it, so this wiring blocks only new debt.

The detection path is not optional politeness. `skills/validate-feature/` ships
via `install.sh` into consumer repositories that have no `packages/gen-eval/`
and no `openspec/contracts/`, where the gate cannot run at all; wiring it
unconditionally would fail every validation in every downstream repo. The
skill's existing gen-eval phase already does detection-plus-printed-SKIP, so
the pattern is in the file being edited. The SKIP is printed rather than silent
for the usual reason — an unprinted skip and a passing gate are the same
observation.

#### Scenario: Gate runs during validation

- **WHEN** `/validate-feature` reaches the spec-compliance phase for a change
- **THEN** it SHALL invoke the traceability gate with `--scope change` and the
  active change's identifier
- **AND** it SHALL invoke the gate bare, not through a pipeline, so the gate's
  exit status is the observed status

#### Scenario: Gate failure fails validation

- **WHEN** the traceability gate exits non-zero
- **THEN** `/validate-feature` SHALL record the validation as failed
- **AND** the validation report SHALL include the gate's output naming the
  violations

#### Scenario: Gate absent in a consumer repository

- **WHEN** `/validate-feature` runs in a repository where
  `packages/gen-eval/scripts/check_traceability.py` or `openspec/contracts/` is
  absent
- **THEN** it SHALL print a SKIP naming the missing path
- **AND** it SHALL NOT record the validation as failed on that account

#### Scenario: Skill wiring is covered by skill tests

- **WHEN** the traceability gate wiring is added to `/validate-feature`
- **THEN** the skill's own tests SHALL assert the gate is invoked in change
  scope and that a non-zero gate exit fails validation
- **AND** they SHALL assert that an absent gate produces a printed SKIP and a
  passing validation
