# project-context-refresh-orchestration — delta

## MODIFIED Requirements

### Requirement: Deterministic context drift gate

The system SHALL provide a single composed drift gate that runs the deterministic context
producers, architecture freshness, and work-package context-impact validation, and emits
one structured report.

The gate SHALL be invocable identically from a developer checkout and from CI, so that a
CI failure is reproducible with one local command.

The gate SHALL resolve the base reference to exactly one revision and record that revision
in the report. Every comparison the gate performs SHALL use the recorded revision. A base
name that could resolve to more than one revision SHALL NOT be resolved differently by
different parts of the same run, because a report that compares against two bases describes
no single tree.

The report SHALL name every stale artifact by repository-relative path rather than
reporting an aggregate count or status alone.

The gate SHALL NOT write to the checkout, and SHALL NOT record a durable operation or
manifest.

#### Scenario: Stale artifacts are named individually
- **GIVEN** a checkout where two managed documentation artifacts are stale
- **WHEN** the drift gate runs
- **THEN** the report SHALL list both artifact paths
- **AND** the gate SHALL exit with the drift exit code

#### Scenario: Gate reproduces locally
- **GIVEN** a CI run that failed on deterministic drift
- **WHEN** an operator runs the documented local gate command at the same revision
- **THEN** the local report SHALL identify the same stale artifacts

#### Scenario: Gate reproduces across environments in both directions
- **GIVEN** one tree at one revision
- **WHEN** the gate runs in a fresh clone and in a long-lived local checkout whose local
  base branch is behind its remote
- **THEN** both runs SHALL report the same outcome and the same exit code
- **AND** both SHALL record the same resolved base revision

#### Scenario: Resolved base is recorded
- **GIVEN** any gate run
- **WHEN** the report is emitted
- **THEN** it SHALL record the revision the base name resolved to
- **AND** a reader SHALL be able to determine that revision without re-running git

#### Scenario: Gate leaves the checkout unchanged
- **GIVEN** a checkout with uncommitted modifications
- **WHEN** the drift gate runs
- **THEN** tracked and untracked checkout state SHALL be byte-identical afterwards
- **AND** no durable refresh operation or manifest SHALL be recorded

### Requirement: Drift classification separates blocking drift from pending state and external degradation

The system SHALL classify producer results into four disjoint groups: blocking drift,
informational drift, absent optional owners, and failures.

The system SHALL additionally attribute each drifted result as either inherited or
introduced. Drift is inherited when the relevant producer inputs already differed from the
producer's recorded revision at the merge base, and introduced otherwise. Attribution is a
separate axis from the four groups: it describes who owns a finding, not how severe it is.

Attribution MAY be determined from the paths that changed between the producer's recorded
revision and the merge base, rather than from input content. Where the two disagree,
attribution SHALL err toward inherited, because falsely blaming a branch for the
integration branch's debt is the failure this attribution exists to prevent.

The classification SHALL be a pure function of recorded producer results and the semantic
index reference, performing no input or output.

The classification SHALL be additive: the existing terminal-outcome decision, the
`OperationState` enumeration, and the durable operation and manifest schemas SHALL remain
unchanged.

#### Scenario: Groups are disjoint
- **GIVEN** producer results containing one drifted producer, one absent optional owner, and one failure
- **WHEN** the classification runs
- **THEN** each result SHALL appear in exactly one group

#### Scenario: Inherited drift names the integration branch as owner
- **GIVEN** a producer whose inputs already differed from its recorded revision at the merge base
- **WHEN** the classification runs
- **THEN** the finding SHALL be attributed as inherited
- **AND** the report SHALL name the integration branch as its owner

#### Scenario: Introduced drift is attributed to the branch
- **GIVEN** a branch that changes a relevant producer input
- **AND** a merge base at which that producer was fresh
- **WHEN** the classification runs
- **THEN** the finding SHALL be attributed as introduced

#### Scenario: Ambiguous attribution errs toward inherited
- **GIVEN** a finding whose ownership cannot be determined from the available evidence
- **WHEN** the classification runs
- **THEN** the finding SHALL be attributed as inherited
- **AND** the report SHALL record that the attribution was indeterminate

#### Scenario: Existing outcome decision is unaffected
- **GIVEN** any set of producer results and semantic index reference
- **WHEN** the terminal-outcome decision runs
- **THEN** its result SHALL be identical to its result before this change

### Requirement: Gate exit codes derive from the classification

The gate SHALL exit one when any producer failed or architecture provenance is
unverifiable, two when blocking drift is present without failures, and zero when only
informational drift or absent optional owners are present.

On a pull-request event, inherited blocking drift SHALL NOT contribute to the drift exit
code, and SHALL be reported instead. Introduced blocking drift SHALL contribute to the
drift exit code on every event. On integration-branch and merge-queue events, all blocking
drift SHALL contribute, because at those points there is no other branch to inherit from.

A surviving absent-optional-owner result SHALL NOT fail the gate, because a required
producer reporting no configuration is already rewritten to a failure by registry policy;
only optional owners can remain, and an absent optional owner is external degradation.

The gate's exit-code mapping SHALL NOT alter the exit codes of the existing per-producer
or orchestrated check entry points.

#### Scenario: Failure outranks drift
- **GIVEN** one failed producer and one drifted producer
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit one

#### Scenario: Inherited drift alone does not fail a pull request
- **GIVEN** a pull request whose only blocking findings are attributed as inherited
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit zero
- **AND** the report SHALL list the inherited findings with the integration branch as owner

#### Scenario: Introduced drift fails a pull request
- **GIVEN** a pull request with one blocking finding attributed as introduced
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit with the drift exit code

#### Scenario: Inherited drift blocks on the integration branch
- **GIVEN** an integration-branch or merge-queue event with inherited blocking drift
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit with the drift exit code

#### Scenario: Absent optional owner alone passes
- **GIVEN** one absent optional owner and no drift or failures
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit zero

#### Scenario: Existing entry points keep their codes
- **GIVEN** a checkout with deterministic drift
- **WHEN** the existing orchestrated check entry point runs
- **THEN** its exit code SHALL be unchanged from before this change

### Requirement: Context-impact validation is scoped to changed work-package declarations

The gate SHALL validate work-package context-impact declarations only for work-package
files present in the diff under test, and SHALL NOT enable strict legacy enforcement.

A changed path SHALL be attributed to a work package only when that package's declared
scope covers the path. A work-package file that is itself present in the diff SHALL NOT
thereby acquire responsibility for unrelated changed paths in the same diff. Archiving a
change moves its work-package file into the diff while the surrounding commit regenerates
unrelated artifacts, so co-presence in a diff is not evidence of authorship.

Strict legacy enforcement would fail on work-package files that predate the declaration
contract; progressive enforcement keyed on whether a declaration block exists is the
intended migration path, and closing it is a separate change.

A usage or configuration error from the validator SHALL be reported as an apparatus
failure rather than as drift, because the validator's usage error code collides with the
drift exit code.

#### Scenario: Unchanged packages are not reported
- **GIVEN** a diff touching one work-package file
- **WHEN** the drift gate runs
- **THEN** only that work-package file SHALL be validated

#### Scenario: Co-present work-package files are not blamed for unrelated paths
- **GIVEN** a commit that both moves a work-package file and changes paths outside that package's declared scope
- **WHEN** the drift gate runs
- **THEN** the moved work-package file SHALL NOT be reported as undeclared for those paths

#### Scenario: Legacy packages without declarations pass
- **GIVEN** a changed work-package file with no context-impact declaration block
- **WHEN** the drift gate runs
- **THEN** the package SHALL be reported as unmigrated
- **AND** the gate SHALL NOT fail on that basis

#### Scenario: Validator usage error is an apparatus failure
- **GIVEN** an unreadable context-impact rule table
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit one
- **AND** the report SHALL record an apparatus failure rather than drift

## ADDED Requirements

### Requirement: Gate event coverage is normative

The drift gate SHALL run as a single continuous-integration job on every declared event —
pull requests, merge-queue events, and pushes to the integration branch — and SHALL NOT be
guarded off any of them.

Event-dependent behaviour SHALL be expressed inside the job rather than by preventing the
job from running, because a required check that does not run on a merge-queue event is not
a check on the merge candidate, and a job that reports success on an event it has no rule
for is an unfalsifiable green.

An event the gate has no rule for SHALL be treated as an error rather than as a pass.

#### Scenario: Gate runs on every declared event
- **GIVEN** the continuous-integration configuration
- **WHEN** it is inspected for the drift gate job
- **THEN** the job SHALL run on pull requests, merge-queue events, and integration-branch pushes
- **AND** the job SHALL NOT be conditioned on the event name at the job level

#### Scenario: Unknown event fails loudly
- **GIVEN** the gate job triggered by an event it has no rule for
- **WHEN** the job runs
- **THEN** it SHALL fail
- **AND** it SHALL NOT report success

### Requirement: Automated remediation is confined to dependency-update pull requests

Where the system automatically regenerates deterministic context artifacts and commits them
back to a pull-request branch, that automation SHALL apply only to pull requests opened by
the dependency-update bot, and SHALL cover only producers that are inexpensive and
byte-deterministic. The architecture producer SHALL be excluded.

The automation SHALL regenerate against a base that is current, because artifacts derived
from a stale base are themselves drift.

The command the automation runs to regenerate SHALL be the same command, with the same
arguments, that the gate runs to check. A checker and a writer invoked differently will
disagree permanently on an artifact that is in fact correct.

Write permission SHALL be granted to that job alone and SHALL NOT be granted at the
workflow level.

#### Scenario: Dependency-update pull request is remediated
- **GIVEN** a pull request opened by the dependency-update bot with inherited deterministic drift
- **WHEN** the remediation job runs
- **THEN** it SHALL regenerate the inexpensive deterministic artifacts
- **AND** it SHALL commit them to the pull-request branch

#### Scenario: Human pull request is not written to
- **GIVEN** a pull request opened by a person
- **WHEN** the remediation job runs
- **THEN** it SHALL make no commit
- **AND** it SHALL make no push

#### Scenario: Write permission is scoped to the remediation job
- **GIVEN** the continuous-integration configuration
- **WHEN** its permissions are inspected
- **THEN** no workflow-level grant of repository write access SHALL be present
- **AND** only the remediation job SHALL declare it
