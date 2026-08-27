# project-context-refresh-orchestration Specification

## Purpose
TBD - created by archiving change implement-project-context-refresh-orchestration. Update Purpose after archive.
## Requirements
### Requirement: Unified context refresh command

The system SHALL provide one refresh-project-context command that, for an explicit
repository and full source Git revision, runs every configured context producer and
emits a manifest that validates against the ri-06 refresh-manifest schema. The
command SHALL orchestrate only configured producers and SHALL NOT define its own
result, manifest, or operation model.

<!-- Scenario ID: project-context-refresh-orchestration.runs-all-configured -->
#### Scenario: One command runs all configured producers

- **WHEN** the refresh command runs for a repository at a full source Git revision
- **THEN** it SHALL invoke each configured deterministic producer, the architecture
  producer, and the semantic-index producer through their canonical owners
- **AND** it SHALL record every producer result on one canonical operation for that
  repository and revision
- **AND** it SHALL emit a manifest that validates against the ri-06
  `context-refresh-manifest` schema
- **AND** the manifest `refresh_status` SHALL equal the finalized operation outcome

<!-- Scenario ID: project-context-refresh-orchestration.capability-follow-up -->
#### Scenario: Unconfigured producers are not fabricated

- **WHEN** the proposal names a producer that has no canonical owner configured
- **THEN** the refresh command SHALL omit it rather than invent an implementation
- **AND** the omission SHALL be recorded as a documented follow-up, not a failure

### Requirement: Idempotent revision-addressed refresh

A second refresh for the same repository revision SHALL reuse the single canonical
operation and SHALL produce no repository diff. The command SHALL reuse or verify the
existing semantic-index operation rather than start a duplicate pipeline.

<!-- Scenario ID: project-context-refresh-orchestration.no-diff-on-rerun -->
#### Scenario: Repeat refresh produces no repository diff

- **WHEN** the refresh command runs twice for the same revision, inputs, and producer
  versions
- **THEN** the second run SHALL reuse the same canonical operation identity
- **AND** deterministic producer outputs SHALL remain byte-identical
- **AND** the working tree SHALL show no change attributable to the rerun
- **AND** the semantic-index reference SHALL be reused or re-verified, not duplicated

### Requirement: Semantic-index degradation isolation

Failure or unavailability of the semantic index SHALL NOT corrupt or discard any
successful deterministic producer output. Deterministic and architecture producer
results SHALL be recorded before the semantic index is attempted, and a non-succeeded
semantic index SHALL be represented as a degraded reference with a bounded fallback.

<!-- Scenario ID: project-context-refresh-orchestration.semantic-degradation -->
#### Scenario: Semantic failure preserves deterministic output

- **WHEN** the semantic index is unavailable or errors during a refresh
- **THEN** all previously recorded deterministic and architecture results SHALL
  remain intact on the operation
- **AND** the semantic index SHALL be recorded as a non-succeeded reference carrying a
  bounded fallback, not as a failed deterministic producer
- **AND** the operation SHALL finalize as degraded rather than failed
- **AND** the emitted manifest SHALL still contain the successful deterministic output

### Requirement: Preserved producer ownership

Each producer SHALL remain independently runnable, and every refresh result SHALL
be attributable to the canonical owner of its producer. Producer identity SHALL be
carried by the stable producer ID, which SHALL map to exactly one canonical owner
through the producer registry; the refresh output SHALL surface that owner so the
aggregate never collapses per-producer identity or ownership.

<!-- Scenario ID: project-context-refresh-orchestration.independent-producer -->
#### Scenario: A single producer runs independently

- **WHEN** the refresh command is invoked for one named producer
- **THEN** it SHALL run only that producer and report exactly one result
- **AND** the result SHALL carry that producer's stable ID
- **AND** the refresh output SHALL resolve that stable ID to its canonical owner
  via the producer registry

### Requirement: Sync-point-only main writes

No refresh path SHALL write canonical main outputs except from a managed worktree or from an explicitly authorized sync-point operation that has enforced its clean-tree, active-agent, and exclusive-lock guards.

The refresh command SHALL keep the OpenSpec projection read-only, SHALL write the
durable manifest to a location that never mutates the tracked working tree, and
SHALL refuse an unauthorized shared or bare checkout exactly as before. Sync-point
authorization SHALL be an explicit caller opt-in, never inferred from the
environment, and canonical specification merges SHALL remain the responsibility of
the cleanup operation.

<!-- Scenario ID: project-context-refresh-orchestration.no-main-write -->
#### Scenario: Refresh never writes main directly

- **WHEN** the refresh command runs without sync-point authorization
- **THEN** it SHALL refuse to run against a shared or bare checkout
- **AND** it SHALL write only producer-managed outputs plus a durable manifest kept
  outside the tracked working tree
- **AND** canonical specification merges SHALL remain the responsibility of the
  sync-point cleanup operation

<!-- Scenario ID: project-context-refresh-orchestration.authorized-sync-point -->
#### Scenario: An authorized sync point may refresh main in place

- **WHEN** the refresh command is invoked with explicit sync-point authorization from
  the main-synchronization skill
- **THEN** it SHALL be permitted to write producer-managed outputs in the shared
  checkout on the main branch
- **AND** the caller SHALL have verified a clean working tree, no active agent
  worktrees, and exclusive sync-point access before the write
- **AND** the OpenSpec projection SHALL remain read-only in that mode

<!-- Scenario ID: project-context-refresh-orchestration.deferred-semantic-index -->
#### Scenario: Semantic indexing can be deferred to a later revision

- **WHEN** the refresh command is invoked with the semantic index deferred
- **THEN** it SHALL run every deterministic and architecture producer as usual
- **AND** it SHALL record the semantic index as a pending reference carrying a bounded
  exact-search fallback rather than attempting the index inline
- **AND** the recorded deterministic results SHALL be identical to those of a run that
  attempted the index

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

### Requirement: Branch-local checkpoint mode

The refresh lifecycle SHALL provide a branch-local checkpoint mode that reports the
project context a work package has invalidated, executed inside a feature worktree
against that package's own changed-file list.

The checkpoint reports affected capabilities, APIs, architecture nodes, decisions,
documentation, and the semantic index revision. It is distinct from `generate` and
`check`: it is scope-restricted to one work package and its results are never canonical.

#### Scenario: Checkpoint runs for a work package inside a feature worktree

- **WHEN** a checkpoint is invoked for a change and package inside a managed worktree,
  supplied with that package's changed-file list
- **THEN** it produces a checkpoint report covering all six context surfaces
- **AND** the report records the exact revision the checkpoint was computed against

#### Scenario: Checkpoint refuses to run against a shared checkout

- **WHEN** a checkpoint is invoked from the shared checkout rather than a managed worktree
- **THEN** it refuses to run and reports the checkout-policy violation
- **AND** it writes no report

### Requirement: Checkpoint operation-ledger isolation

A checkpoint SHALL NOT create, modify, or finalize any durable refresh operation record,
and SHALL NOT emit a refresh manifest.

Recorded producer results are immutable for their revision and are reused verbatim by
later refreshes. A checkpoint result is scope-restricted and feature-namespaced, so
admitting one into the canonical ledger would be unrecoverable within the existing
contract.

#### Scenario: Checkpoint leaves the shared operation ledger untouched

- **WHEN** a checkpoint completes for any package
- **THEN** the refresh-operations directory under the repository's git common directory
  contains exactly the entries it contained beforehand
- **AND** no refresh manifest is written

#### Scenario: A later canonical refresh is unaffected by a prior checkpoint

- **WHEN** a checkpoint has run at a revision
- **AND** a canonical refresh is subsequently invoked at that same revision
- **THEN** the refresh computes its own producer results
- **AND** it reuses nothing produced by the checkpoint

### Requirement: Checkpoint semantic index namespace isolation

Checkpoint semantic indexing SHALL target a non-canonical index namespace, so that a
branch cannot mutate or promote into the canonical main index.

The namespace kind is `work_package` and the namespace key identifies the change and
package. Canonical promotion remains gated on the main namespace, so the isolation is
enforced by the index runtime rather than by checkpoint convention.

#### Scenario: Checkpoint indexing uses a work-package namespace

- **WHEN** a checkpoint performs semantic indexing for a package
- **THEN** the index request carries namespace kind `work_package`
- **AND** the namespace key identifies both the change and the package

#### Scenario: Checkpoint indexing cannot promote to the canonical index

- **WHEN** a checkpoint completes semantic indexing
- **THEN** no promotion into the canonical main index occurs
- **AND** the canonical index content is unchanged

#### Scenario: Canonical refresh indexing is unchanged

- **WHEN** the canonical refresh performs semantic indexing
- **THEN** it continues to use the main namespace kind and key

### Requirement: Checkpoint read-scope enforcement

Checkpoint execution SHALL be restricted to the work package's permitted read scope,
resolved as the package's read-allow globs minus its deny globs, with deny taking
precedence.

#### Scenario: Denied paths are excluded from checkpoint indexing

- **WHEN** a package declares a deny glob that overlaps its read-allow globs
- **AND** a checkpoint indexes for that package
- **THEN** paths matching the deny glob are excluded from indexing
- **AND** the exclusion holds even though those paths also match a read-allow glob

#### Scenario: Checkpoint does not read outside the permitted scope

- **WHEN** a checkpoint runs for a package whose read-allow scope excludes a directory
- **THEN** files in that directory are not indexed

### Requirement: Checkpoint artifacts remain isolated from canonical outputs

A checkpoint SHALL NOT modify any tracked producer output, and SHALL execute every
context producer in read-only check mode.

#### Scenario: Tracked producer outputs are unchanged by a checkpoint

- **WHEN** a checkpoint completes for any package
- **THEN** every tracked producer output in the working tree is byte-identical to its
  state before the checkpoint ran

#### Scenario: Producers are invoked in check mode

- **WHEN** a checkpoint invokes a deterministic context producer
- **THEN** the producer runs in check mode
- **AND** the producer's generate path is not invoked

### Requirement: Checkpoint report determinism and location

The checkpoint report SHALL be written to a change-local, version-controlled path and
SHALL be byte-stable for a fixed revision.

The report excludes volatile content — wall-clock timestamps, attempt counters, absolute
paths, and raw exception text — so that re-running a checkpoint at an unchanged revision
produces no repository diff.

#### Scenario: Repeated checkpoints at one revision produce no diff

- **WHEN** a checkpoint runs twice for the same package at the same revision with no
  intervening change
- **THEN** the second run produces a report byte-identical to the first

#### Scenario: Report validates against the checkpoint schema

- **WHEN** a checkpoint report is written
- **THEN** it validates against the published context-checkpoint schema

### Requirement: Checkpoint architecture coverage reports freshness and delta separately

A checkpoint SHALL report architecture freshness and the architecture delta as distinct
findings, and SHALL label a delta computed from a stale artifact as non-authoritative.

Freshness answers whether the branch's architecture artifact is current for the revision;
the delta answers which architecture nodes changed relative to the merge base. A stale
artifact can yield a misleading delta, so the two are never collapsed.

#### Scenario: Stale architecture artifact yields a labelled delta

- **WHEN** a checkpoint runs and the branch's architecture artifact is not fresh for the
  current revision
- **THEN** the report records the artifact as stale
- **AND** the reported architecture delta is marked non-authoritative

#### Scenario: Fresh architecture artifact yields an authoritative delta

- **WHEN** a checkpoint runs and the architecture artifact is fresh for the revision
- **THEN** the report lists the changed architecture nodes relative to the merge base

### Requirement: Checkpoint semantic indexing degrades without failing

Checkpoint semantic indexing SHALL degrade to a recorded fallback when the index is
unavailable or unconfigured, and SHALL NOT fail the checkpoint.

#### Scenario: Missing index configuration degrades the checkpoint

- **WHEN** a checkpoint runs without semantic index configuration present
- **THEN** the report records a not-configured semantic index status with a fallback
- **AND** the deterministic producer findings are still reported in full

#### Scenario: Index error does not discard deterministic findings

- **WHEN** semantic indexing fails during a checkpoint
- **THEN** the report records the failure as a bounded reason
- **AND** every deterministic producer finding is retained

### Requirement: Checkpoint reporting is advisory

A checkpoint SHALL report context drift as data without failing, and SHALL signal failure
only when it could not produce a valid report.

Turning deterministic context drift into a build or merge failure is the responsibility of
the drift-gate capability, which consumes this report.

#### Scenario: Detected drift does not fail the checkpoint

- **WHEN** a checkpoint detects that a context producer reports drift
- **THEN** the drift is recorded in the report
- **AND** the checkpoint reports success

#### Scenario: Inability to produce a report is a failure

- **WHEN** a checkpoint cannot produce a valid report
- **THEN** it reports failure with a bounded reason

