# project-context-refresh-orchestration — delta

## ADDED Requirements

### Requirement: Deterministic context drift gate

The system SHALL provide a single composed drift gate that runs the deterministic context
producers, architecture freshness, and work-package context-impact validation, and emits
one structured report.

The gate SHALL be invocable identically from a developer checkout and from CI, so that a
CI failure is reproducible with one local command.

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

#### Scenario: Gate leaves the checkout unchanged
- **GIVEN** a checkout with uncommitted modifications
- **WHEN** the drift gate runs
- **THEN** tracked and untracked checkout state SHALL be byte-identical afterwards
- **AND** no durable refresh operation or manifest SHALL be recorded

### Requirement: Drift classification separates blocking drift from pending state and external degradation

The system SHALL classify producer results into four disjoint groups: blocking drift,
informational drift, absent optional owners, and failures.

The classification SHALL be a pure function of recorded producer results and the semantic
index reference, performing no input or output.

The classification SHALL be additive: the existing terminal-outcome decision, the
`OperationState` enumeration, and the durable operation and manifest schemas SHALL remain
unchanged.

#### Scenario: Groups are disjoint
- **GIVEN** producer results containing one drifted producer, one absent optional owner, and one failure
- **WHEN** the classification runs
- **THEN** each result SHALL appear in exactly one group

#### Scenario: Existing outcome decision is unaffected
- **GIVEN** any set of producer results and semantic index reference
- **WHEN** the terminal-outcome decision runs
- **THEN** its result SHALL be identical to its result before this change

### Requirement: Projection drift is informational and never blocks

The OpenSpec projection producer's drift SHALL be classified as informational and SHALL
NOT contribute to a failing gate exit code.

Projection drift indicates that an active change carries an unmerged specification delta,
which is the correct state for in-flight work; it does not indicate that committed output
is stale. The canonical specification merge is owned by the archive sync point, not by the
gate.

The report SHALL still include projection findings so the pending-merge surface stays
visible.

#### Scenario: Pending merges do not fail the gate
- **GIVEN** a repository with active changes carrying unmerged specification deltas
- **AND** no other producer reporting drift
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit zero
- **AND** the report SHALL list the projection findings as informational

#### Scenario: Projection drift does not mask blocking drift
- **GIVEN** projection drift and one stale documentation artifact
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit with the drift exit code
- **AND** the documentation artifact SHALL be reported as blocking drift

### Requirement: Architecture freshness fails closed on unverifiable provenance

The architecture producer SHALL determine freshness by comparing committed provenance
against recomputed artifact digests, and SHALL NOT report freshness by rebuilding
provenance from the working tree.

Missing, malformed, or schema-invalid provenance SHALL be reported as drift, not as an
absent optional owner, because unverifiable evidence is not the same as absent tooling.

An architecture owner that is genuinely not importable SHALL remain an absent optional
owner and SHALL NOT fail the gate.

#### Scenario: Missing provenance blocks
- **GIVEN** a checkout with no committed architecture provenance
- **WHEN** the drift gate runs
- **THEN** architecture SHALL be reported as drift
- **AND** the gate SHALL exit with the drift exit code

#### Scenario: Absent owner degrades without blocking
- **GIVEN** a checkout where the architecture refresh owner is not importable
- **AND** no other producer reporting drift
- **WHEN** the drift gate runs
- **THEN** architecture SHALL be reported as an absent optional owner
- **AND** the gate SHALL exit zero

#### Scenario: Stale architecture blocks
- **GIVEN** committed provenance whose digests do not match recomputed artifact digests
- **WHEN** the drift gate runs
- **THEN** architecture SHALL be reported as drift

### Requirement: Gate exit codes derive from the classification

The gate SHALL exit one when any producer failed or architecture provenance is
unverifiable, two when blocking drift is present without failures, and zero when only
informational drift or absent optional owners are present.

A surviving absent-optional-owner result SHALL NOT fail the gate, because a required
producer reporting no configuration is already rewritten to a failure by registry policy;
only optional owners can remain, and an absent optional owner is external degradation.

The gate's exit-code mapping SHALL NOT alter the exit codes of the existing per-producer
or orchestrated check entry points.

#### Scenario: Failure outranks drift
- **GIVEN** one failed producer and one drifted producer
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit one

#### Scenario: Absent optional owner alone passes
- **GIVEN** one absent optional owner and no drift or failures
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit zero

#### Scenario: Existing entry points keep their codes
- **GIVEN** a checkout with deterministic drift
- **WHEN** the existing orchestrated check entry point runs
- **THEN** its exit code SHALL be unchanged from before this change

### Requirement: Semantic index status is reported as not attempted

The gate SHALL report the semantic index as not attempted, with an explicit reason, and
SHALL NOT construct a semantic indexer or probe Postgres or an embedder.

Reporting the index as not configured would assert that a probe found no configuration,
which the gate never performs. Reporting it as not attempted makes no currency claim, so
stale semantic results can never be presented as current.

Semantic index status SHALL NOT contribute to the gate's exit code.

#### Scenario: No probe is performed
- **GIVEN** an environment with complete semantic index configuration present
- **WHEN** the drift gate runs
- **THEN** no semantic indexer SHALL be constructed
- **AND** the report SHALL record the semantic status as not attempted with a reason

#### Scenario: Semantic status never gates
- **GIVEN** an environment with no semantic index configuration
- **AND** no producer reporting drift or failure
- **WHEN** the drift gate runs
- **THEN** the gate SHALL exit zero

### Requirement: Check-mode read-only behaviour is asserted for every registered producer

The system SHALL assert, for every producer returned by the producer registry, that
running it in check mode against a modified checkout leaves both tracked and untracked
paths byte-identical.

The assertion SHALL enumerate producers from the registry rather than from a fixed list,
so that producers registered after this change are covered.

The registry SHALL NOT be given a runtime filesystem guard; the assertion is the
enforcement mechanism, and the absence of a runtime guard is deliberate rather than an
omission.

#### Scenario: A writing producer is caught
- **GIVEN** a producer that writes to the checkout in check mode
- **WHEN** the read-only assertion runs
- **THEN** the assertion SHALL fail and name the producer

#### Scenario: Untracked writes are caught
- **GIVEN** a producer that writes an untracked scratch file in check mode
- **WHEN** the read-only assertion runs
- **THEN** the assertion SHALL fail

#### Scenario: Newly registered producers are covered
- **GIVEN** a producer registered after this change
- **WHEN** the read-only assertion runs
- **THEN** that producer SHALL be included without editing the assertion

### Requirement: The gate is the single freshness authority for the decision index

The drift gate SHALL be the only continuous-integration check that verifies decision index
freshness, and the previous regenerate-and-compare job SHALL be removed.

The gate SHALL detect an orphaned capability file whose content is unchanged but whose
presence is stale, because the removed job could not detect it by comparing content alone.

#### Scenario: Orphaned capability file is detected
- **GIVEN** a decision index containing a capability file for a capability with no tagged decisions
- **AND** that file's content is unchanged
- **WHEN** the drift gate runs
- **THEN** the file SHALL be reported as drift

#### Scenario: Only one decision freshness check exists
- **WHEN** the continuous-integration configuration is inspected
- **THEN** exactly one check SHALL verify decision index freshness

### Requirement: Context-impact validation is scoped to changed work-package declarations

The gate SHALL validate work-package context-impact declarations only for work-package
files present in the diff under test, and SHALL NOT enable strict legacy enforcement.

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
