# Project Context Refresh Orchestration — branch-local checkpoints

## ADDED Requirements

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
