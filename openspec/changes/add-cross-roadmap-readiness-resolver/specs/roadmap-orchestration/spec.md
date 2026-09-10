# roadmap-orchestration Delta

## ADDED Requirements

### Requirement: Canonical Cross-Roadmap Readiness Resolution

The roadmap runtime SHALL expose a read-only repository-wide resolver that uses roadmap definitions plus canonical checkpoint state to emit one globally ranked ready-now list. The admission function `_get_ready_items` MUST have exactly one source definition in `roadmap-runtime` and SHALL be imported by both `autopilot-roadmap` and the repository-wide resolver.

#### Scenario: Return one globally ranked ready-now list

- **WHEN** the resolver scans multiple active roadmap workspaces containing dependency-ready items
- **THEN** it SHALL return one flat list sorted by priority, roadmap id, and item id
- **AND** each entry SHALL carry roadmap id, item id, priority, and effort.

#### Scenario: Preserve the existing autopilot admission contract

- **WHEN** autopilot asks for ready items in one roadmap
- **THEN** the shared helper SHALL admit only approved or in-progress items whose local and external prerequisites are complete
- **AND** it SHALL exclude checkpoint-completed, checkpoint-failed, superseded, and `superseded_by` items.

#### Scenario: Use one shared implementation

- **WHEN** the repository's Python sources are inspected by AST
- **THEN** exactly one function definition named `_get_ready_items` SHALL exist under `skills/`
- **AND** both the autopilot orchestrator and repository-wide resolver SHALL import that definition from `roadmap-runtime`.

### Requirement: Checkpoint-Authoritative Cross-Roadmap Edges

The resolver SHALL treat a present valid checkpoint's completed and failed terminal sets as authoritative for its roadmap, and SHALL use roadmap item status only when the checkpoint is absent as a valid never-started state. Typed `external_depends_on` edges MUST remain blocked until their effective external prerequisite is completed.

#### Scenario: External prerequisite completion unblocks without dependent edits

- **GIVEN** supervisor item `ri-04` has `external_depends_on: [roadmap-always-on-agent-automation:ri-06]`
- **WHEN** always-on `ri-06` is incomplete in its effective state
- **THEN** supervisor `ri-04` SHALL be absent from ready output
- **AND** when the always-on checkpoint records `ri-06` completed, `ri-04` SHALL become ready without editing the supervisor roadmap.

#### Scenario: Checkpoint terminal state overrides stale roadmap status

- **WHEN** a valid checkpoint records an item completed or failed while its roadmap definition still says approved or in-progress
- **THEN** the resolver SHALL exclude that item from ready output
- **AND** external dependents SHALL observe completion only for the checkpoint-completed case.

#### Scenario: Invalid checkpoint fails closed

- **WHEN** a checkpoint is malformed, names a different roadmap, references unknown terminal item ids, or contradicts its own terminal sets
- **THEN** the resolver SHALL mark that workspace stale with a bounded reason code
- **AND** it SHALL withhold that workspace's items and completion refs instead of reconstructing state from advisory artifacts.

### Requirement: Deterministic Readiness Projection

The resolver SHALL derive its output only from active `roadmap.yaml` files and sibling `checkpoint.json` state. Its JSON output MUST contain a SHA-256 `source_fingerprint` over canonical readiness-relevant input, a content-consistency `stale` signal, and bounded diagnostics. A downstream projection can detect staleness by comparing its stored source fingerprint with a newly resolved fingerprint. It SHALL NOT contain a generated timestamp or depend on mtimes, learnings, handoffs, coordinator state, or queue projections.

#### Scenario: Unchanged inputs produce byte-identical output

- **WHEN** the readiness command runs twice with no roadmap or checkpoint content change
- **THEN** the two stdout byte streams SHALL be identical
- **AND** their source fingerprints SHALL be identical
- **AND** ready entries, diagnostics, and keys SHALL use deterministic ordering.

#### Scenario: Missing checkpoint is a valid first run

- **WHEN** a valid roadmap workspace has no checkpoint and no advisory record claims prior progress
- **THEN** the resolver SHALL evaluate roadmap definition status as the never-started baseline
- **AND** it SHALL report `checkpoint_absent` without marking the report stale.

#### Scenario: Advisory state cannot change readiness

- **WHEN** learning, handoff, or queue artifacts change while every roadmap and checkpoint remains byte-identical
- **THEN** the resolver output SHALL remain byte-identical.

