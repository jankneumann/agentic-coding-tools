## ADDED Requirements

### Requirement: Architecture Provenance Evidence

Every successful architecture refresh MUST write
`docs/architecture-analysis/architecture.provenance.json` conforming to the published
architecture provenance schema. It SHALL identify the repository, exact analyzed Git
SHA, dirty state, architecture producer/version, mode, relevant input fingerprint,
deterministic timestamp, optional-tool identity, validation outcome, and sorted owned
artifacts with SHA-256 digests.

<!-- Scenario ID: architecture-refresh.1 -->
#### Scenario: Clean revision produces complete provenance

- **WHEN** a full architecture refresh succeeds in a clean Git worktree
- **THEN** provenance SHALL record exact `HEAD`, `worktree_dirty=false`, producer
  version, input fingerprint, and every required artifact digest

<!-- Scenario ID: architecture-refresh.2 -->
#### Scenario: Dirty relevant input is represented truthfully

- **WHEN** relevant tracked or untracked input differs from `HEAD`
- **THEN** provenance SHALL retain `HEAD` as the analyzed revision
- **AND** SHALL set `worktree_dirty=true`
- **AND** the fingerprint SHALL describe working-tree bytes

### Requirement: Content-Based Architecture Freshness

Architecture freshness MUST be determined from schema-valid provenance, current
relevant-input identity, producer identity, mode, and owned-artifact digests. Mtimes
and elapsed wall-clock age MUST NOT decide freshness.

<!-- Scenario ID: architecture-refresh.3 -->
#### Scenario: Mtime-only change stays fresh

- **WHEN** identity and bytes are unchanged but artifact mtimes change
- **THEN** check mode SHALL report `fresh`
- **AND** affected-test selection SHALL accept the graph

<!-- Scenario ID: architecture-refresh.3b -->
#### Scenario: Artifact-only convergence commit does not self-invalidate

- **WHEN** a later commit changes only provenance-owned architecture artifacts
- **THEN** check mode SHALL report `fresh` when relevant fingerprints agree
- **AND** SHALL retain the analyzed source commit as provenance

<!-- Scenario ID: architecture-refresh.4 -->
#### Scenario: Relevant input change is stale immediately

- **WHEN** a relevant source/config file is added, removed, renamed, or modified
- **THEN** check mode SHALL report `INPUT_FINGERPRINT_MISMATCH`
- **AND** a recent graph mtime SHALL NOT override it

<!-- Scenario ID: architecture-refresh.5 -->
#### Scenario: Architecture producer change invalidates freshness

- **WHEN** architecture producer or output-affecting tool identity changes
- **THEN** check mode SHALL report stale and name producer identity as the cause

<!-- Scenario ID: architecture-refresh.6 -->
#### Scenario: Invalid provenance fails closed

- **WHEN** provenance is missing, malformed, or schema-invalid
- **THEN** check mode SHALL never report fresh
- **AND** affected-test selection SHALL use its full-suite fallback

### Requirement: Read-Only Precise Check Mode

The architecture runner SHALL provide machine-readable `--check` that writes neither
repository files nor shared runtime records. It MUST exit zero only for `fresh` and
report exact reason codes plus stale artifact paths.

<!-- Scenario ID: architecture-refresh.7 -->
#### Scenario: Check identifies exact artifact drift

- **WHEN** one owned artifact is modified and another is missing
- **THEN** check mode SHALL report both paths with distinct reason codes
- **AND** SHALL leave all files byte-identical

### Requirement: Deterministic Staged Generation

The architecture producer SHALL emit byte-identical repository artifacts for the same
revision, working bytes, producer version, configuration, mode, and optional-tool
identity. It SHALL stage and validate the selected set before promotion.

<!-- Scenario ID: architecture-refresh.8 -->
#### Scenario: Pipeline failure preserves last known-good artifacts

- **WHEN** an analyzer/compiler/validation step fails before promotion
- **THEN** no staged partial file SHALL replace committed architecture artifacts
- **AND** the previous provenance SHALL remain intact

<!-- Scenario ID: architecture-refresh.9 -->
#### Scenario: Repeat refresh has no repository diff

- **WHEN** refresh repeats with identical identity
- **THEN** repository artifact bytes SHALL remain identical
- **AND** Git SHALL show no second architecture diff

### Requirement: Canonical Project-Context Producer Integration

Architecture refresh MUST reuse `project-context-runtime` from
`add-durable-context-refresh-records` for repository/revision operation identity,
Git-common-dir locking, atomic operation persistence, safe errors, transitions, and
canonical `ProducerResult`. It MUST NOT define or write an architecture-specific
operation ledger or shared producer-result schema.

<!-- Scenario ID: architecture-refresh.10 -->
#### Scenario: Architecture records one canonical producer result

- **WHEN** architecture generation/check completes for a shared operation
- **THEN** the adapter SHALL call the supported runtime facade
- **AND** SHALL record exactly one `producer_id=architecture` result with canonical
  status, artifacts, validations, remediation, fallback, and safe error fields

<!-- Scenario ID: architecture-refresh.11 -->
#### Scenario: Separate process observes architecture result

- **WHEN** one process records architecture output in the canonical operation
- **AND** another process queries the RPC facade for that operation
- **THEN** it SHALL observe the persisted architecture producer result
- **AND** no process-local handle SHALL be required

<!-- Scenario ID: architecture-refresh.12 -->
#### Scenario: Duplicate trigger reuses canonical operation

- **WHEN** the same repository/revision operation already contains a fresh architecture
  result whose provenance/digests still validate
- **THEN** trigger SHALL return the canonical operation ID with `is_new=false`
- **AND** no duplicate architecture pipeline SHALL start

<!-- Scenario ID: architecture-refresh.13 -->
#### Scenario: Adapter does not finalize multi-producer operation

- **WHEN** architecture records a fresh, degraded, or failed producer result
- **THEN** it SHALL NOT call the runtime's whole-operation `finalize`
- **AND** ri-07 orchestration SHALL remain responsible for the global terminal outcome

### Requirement: Additive Architecture RPC Status Facade

The RPC SHALL project canonical operation/architecture-result evidence onto existing
method names and status strings. Deprecated `max_age_hours` and `graph_mtime` MAY
remain but MUST NOT affect freshness.

<!-- Scenario ID: architecture-refresh.14 -->
#### Scenario: Existing caller receives additive response

- **WHEN** a caller invokes `is_graph_stale(max_age_hours=6)`
- **THEN** legacy response fields SHALL remain
- **AND** source SHA, producer version, fingerprint, provenance path, shared operation
  ID, and freshness reason SHALL be added

<!-- Scenario ID: architecture-refresh.15 -->
#### Scenario: Invalid shared evidence degrades safely

- **WHEN** the coordinator client encounters transport failure, malformed provenance,
  or a corrupt/schema-incompatible shared operation
- **THEN** it SHALL return `RefreshClientUnavailable` rather than raise
- **AND** merge-train full-suite fallback SHALL remain available
