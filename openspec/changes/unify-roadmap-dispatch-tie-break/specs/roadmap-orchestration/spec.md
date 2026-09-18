## ADDED Requirements

### Requirement: Roadmap List Order Breaks Priority Ties

Every roadmap dispatch path SHALL break ties among equal-priority ready items by the item's position in its roadmap's `items` list, and SHALL NOT use `item_id` as an ordering key. Position SHALL be carried as declared data rather than inferred from the order in which ready items are passed between functions.

#### Scenario: One order across execution modes

- **WHEN** two dependency-ready items share a priority and their roadmap list order contradicts their `item_id` order
- **THEN** sequential readiness, coordinated batch selection, and the cross-roadmap resolver SHALL rank them identically, in roadmap list order.

#### Scenario: Declared position survives caller re-ordering

- **WHEN** ready items are passed to coordinated batch selection in an order other than roadmap list order
- **THEN** selection SHALL order them by their declared position, not by argument order.

#### Scenario: Naming the first ready item agrees with dispatch

- **WHEN** a surface outside dispatch names a roadmap's first ready item, such as the supervisor mirror recording a parked `roadmap_approval` gate's `change_id`
- **THEN** it SHALL resolve "first" by the same order, so the name it records is the item dispatch will select.

#### Scenario: Reordering within a tier takes effect

- **WHEN** an operator reorders an item ahead of a same-priority item without changing either priority
- **THEN** the move SHALL change dispatch order in both sequential and coordinated modes.

## MODIFIED Requirements

### Requirement: Scope-Safe Ready Batches

The roadmap orchestrator MUST admit multiple items to the same ready batch only when their aggregated declared write scopes and lock keys prove that they are independent.

#### Scenario: Fan out disjoint ready items
- **WHEN** two dependency-ready items have valid work packages with disjoint `write_allow` scopes and lock keys
- **THEN** both items are emitted in the same prepared host batch without invoking `dispatch_fn`
- **AND** a synchronization-barrier test observes both host task handles live before either result is awaited

#### Scenario: Serialize overlapping or indeterminate items
- **WHEN** ready items overlap by write scope or lock key, or either item has missing, invalid, empty, or boundless write-scope evidence
- **THEN** the items are not admitted to the same batch and each affected request carries `proof: serial_indeterminate` with a schema-valid possibly empty `write_allow`
- **AND** deterministic priority and roadmap-list-position ordering selects the first item while the remainder stay ready

#### Scenario: Treat ambiguous glob intersection conservatively
- **WHEN** two items declare globs whose intersection cannot be disproven, including `a/*/c` versus `a/b/*`
- **THEN** the classifier returns `ambiguous` rather than `disjoint`
- **AND** all package scopes, including integration and runtime-mirror write scopes, participate in the decision

### Requirement: Canonical Cross-Roadmap Readiness Resolution

The roadmap runtime SHALL expose a read-only repository-wide resolver that uses roadmap definitions plus canonical checkpoint state to emit one globally ranked ready-now list. The admission function `_get_ready_items` MUST have exactly one source definition in `roadmap-runtime` and SHALL be imported by both `autopilot-roadmap` and the repository-wide resolver.

#### Scenario: Return one globally ranked ready-now list

- **WHEN** the resolver scans multiple active roadmap workspaces containing dependency-ready items
- **THEN** it SHALL return one flat list sorted by priority, roadmap id, and roadmap list position
- **AND** each entry SHALL carry roadmap id, item id, priority, and effort.

#### Scenario: Preserve the existing autopilot admission contract

- **WHEN** autopilot asks for ready items in one roadmap
- **THEN** the shared helper SHALL admit only approved or in-progress items whose local and external prerequisites are complete
- **AND** it SHALL exclude checkpoint-completed, checkpoint-failed, superseded, and `superseded_by` items.

#### Scenario: Use one shared implementation

- **WHEN** the repository's Python sources are inspected by AST
- **THEN** exactly one function definition named `_get_ready_items` SHALL exist under `skills/`
- **AND** both the autopilot orchestrator and repository-wide resolver SHALL import that definition from `roadmap-runtime`.
