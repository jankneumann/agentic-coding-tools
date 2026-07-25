## ADDED Requirements

### Requirement: Documentation sync lifecycle superseded

The standalone `update-documentation` skill and its integration wiring SHALL NOT
be implemented; this change is superseded by
`add-deterministic-context-producer-checks`, which owns the deterministic
`documentation.inventory` producer within the shared project-context refresh
lifecycle. The marker-preserving inventory and prose-preservation behavior
described in this change's retained design is carried forward by that producer.

The superseded proposal's standalone lifecycle wiring (commit-time hooks,
merge-time documentation synchronization, cleanup-feature and validate-feature
gates, and automatic follow-up commits) SHALL NOT be created. Deterministic
context drift gates are owned by `add-deterministic-context-drift-gates` (ri-10)
and main convergence by `integrate-main-context-convergence` (ri-11).

#### Scenario: Superseded change is not dispatchable

- **WHEN** a workflow inspects `add-update-documentation-skill`
- **THEN** it SHALL find no executable task or work package
- **AND** it SHALL find no normative requirement directing commit-time hooks,
  merge-time documentation synchronization, gate integration, or automatic
  follow-up commits
- **AND** it SHALL treat `add-deterministic-context-producer-checks` as the
  replacement that owns the documentation producer
