# fitness-functions Specification

## ADDED Requirements

### Requirement: NFR Capture in Planning Templates

The `feature-workflow` templates `proposal.md` and `design.md` SHALL provide a
Non-Functional Requirements section where each entry states a quality attribute, an
objective metric, a measurable target, and the validation phase that verifies it.
Vague adjectives without a metric SHALL NOT satisfy the section. The `plan-feature`
discovery rubric SHALL include an NFR elicitation category prompting for the
architectural qualities the feature touches and their acceptance thresholds.

#### Scenario: Proposal template contains NFR section

**WHEN** `openspec/schemas/feature-workflow/templates/proposal.md` is read
**THEN** it SHALL contain a `## Non-Functional Requirements` section
**AND** the section SHALL prompt for attribute, metric, target, and verifying phase

#### Scenario: Design template maps NFRs to fitness functions

**WHEN** `openspec/schemas/feature-workflow/templates/design.md` is read
**THEN** it SHALL contain a fitness-function mapping subsection linking each declared
NFR to the check that verifies it

#### Scenario: Discovery rubric elicits NFRs

**WHEN** `skills/plan-feature/SKILL.md` discovery question categories are read
**THEN** an NFR elicitation category SHALL be present alongside the existing six
categories

### Requirement: Consensus Preserves Finding Axis

The consensus synthesizer SHALL parse, retain, and emit the `axis` field of every
finding, and SHALL use `axis` together with `file_path` and `line_range` when matching
findings across vendors, as documented in the parallel-review skills.

#### Scenario: Axis round-trips through consensus

**WHEN** findings carrying `axis` values are synthesized into a consensus report
**THEN** each consensus finding SHALL retain the agreed `axis` value

#### Scenario: Cross-vendor matching uses axis

**WHEN** two vendors report findings at the same `file_path` and overlapping
`line_range` but different `axis` values
**THEN** the findings SHALL NOT be merged into a single consensus finding

### Requirement: Schema-Valid Linter Findings

The validate-feature architecture linters (`dependency_direction`, `file_size`,
`naming_conventions`) SHALL emit findings that validate against
`review-findings.schema.json`, including the required `axis` and `severity` fields.
The linter test suite SHALL assert schema validity with `jsonschema.validate`.

#### Scenario: Linter findings validate against the schema

**WHEN** any architecture linter emits a finding
**THEN** the finding SHALL validate against `review-findings.schema.json` without errors

#### Scenario: Linter tests enforce schema validity

**WHEN** the linter test suite runs
**THEN** at least one test SHALL validate emitted findings against the loaded schema
**AND** the suite SHALL fail if a linter omits a required field

### Requirement: Architecture Gate Ratchet

The validate-feature Architecture phase SHALL be governed by a `gates.architecture`
section in `architecture.config.yaml` with a `mode` of `advisory` or `blocking` and
populated `severity_thresholds`. The gate's thresholds SHALL live in the gate's own
namespace, distinct from `health.severity_thresholds`, which belongs to the
architecture report and is graded in a different vocabulary. In `advisory` mode, findings SHALL be reported
prominently in `validation-report.md` without failing the gate. In `blocking` mode, the
Architecture phase SHALL be a required phase in `gate_logic.py`, and a new dependency
cycle detected by the architecture diff SHALL be a critical finding that fails the hard
gate. The shipped default SHALL be `advisory`; the flip to `blocking` SHALL be a
one-line config change and SHALL be recorded with a date and rationale.

#### Scenario: Advisory mode reports without failing

**WHEN** the Architecture phase runs with `gates.architecture.mode: advisory` and
findings exist
**THEN** `validation-report.md` SHALL list the findings with their severities
**AND** the validation run SHALL NOT fail because of them

#### Scenario: Blocking mode fails on new dependency cycle

**WHEN** `gates.architecture.mode` is `blocking` and the architecture diff detects a new
dependency cycle
**THEN** the hard gate SHALL report the Architecture phase as failed
**AND** the merge SHALL be blocked until the cycle is removed or the finding is
explicitly waived with a recorded reason

#### Scenario: Thresholds are populated

**WHEN** `architecture.config.yaml` is read
**THEN** `gates.architecture.severity_thresholds` SHALL contain at least one
category-to-severity mapping
**AND** `gates.architecture.mode` SHALL be present with value `advisory` or `blocking`

#### Scenario: Gate thresholds do not share the report's namespace

**WHEN** `health.severity_thresholds` is read
**THEN** it SHALL NOT contain severities from the gate vocabulary
(`critical` / `major` / `minor`), since that key is graded
`error` / `warning` / `info` by the architecture report

### Requirement: Coverage Signal With No-Decrease Ratchet

CI SHALL measure line coverage for the coordinator and skills test suites and publish
the percentages in the job output. A coverage baseline SHALL be stored in the
repository, and a ratchet check SHALL compare measured coverage against the baseline,
failing when coverage decreases by more than the configured tolerance. The ratchet job
SHALL start as a non-required status check; its promotion command SHALL be documented
alongside the existing context-drift-gate promotion note.

#### Scenario: CI reports coverage

**WHEN** the CI test jobs complete
**THEN** the job output SHALL include a line-coverage percentage for each measured suite

#### Scenario: Ratchet fails on decrease

**WHEN** measured coverage is below the stored baseline by more than the tolerance
**THEN** the ratchet check SHALL exit non-zero
**AND** the output SHALL name the suite, the baseline, and the measured value

#### Scenario: Maintainer advances baseline on improvement

**WHEN** measured coverage on the default branch exceeds the stored baseline
**THEN** the CI output SHALL print the exact `--update` command needed to persist the
improved measurements
**WHEN** a maintainer runs that command and commits the result
**THEN** improved suite baselines SHALL be updated to the measured values
**AND** no suite baseline SHALL move downward

### Requirement: Degraded Gate Transparency

Every gate that can fall back to a permissive result SHALL record an explicit
`DEGRADED` status distinct from `PASS`, naming what could not be checked and why. This
applies at minimum to: the autopilot GATEKEEPER verdict when no dispatch adapter is
available, multi-vendor review when fewer than two vendors are detected, security
validation under `--allow-degraded-pass`, and any validation phase whose checker was
unavailable. `gate_logic.py` SHALL treat `DEGRADED` as distinct from `PASS`: the soft
gate SHALL warn, and the hard gate SHALL NOT accept a `DEGRADED` required phase without
an explicit, logged override flag.

#### Scenario: Degraded gate writes DEGRADED status

**WHEN** a gate falls back to a permissive result because its checker was unavailable
**THEN** `validation-report.md` SHALL record that phase with status `DEGRADED`
**AND** the entry SHALL name the missing capability

#### Scenario: Hard gate distinguishes DEGRADED from PASS

**WHEN** a required phase reports `DEGRADED` and no override flag is provided
**THEN** the pre-merge hard gate SHALL block
**AND** the block message SHALL state that the phase was not checked rather than failed

#### Scenario: Override is explicit and logged

**WHEN** the operator passes the documented override flag for a `DEGRADED` required
phase
**THEN** the gate SHALL pass
**AND** the override SHALL be recorded in the gate summary with the phase name
