# roadmap-orchestration Specification (delta)

## ADDED Requirements

### Requirement: Policy Engine Uses Catalog Pricing

The roadmap vendor-switch policy SHALL estimate cost deltas from catalog pricing (per-Mtok rates
and observed usage) instead of hardcoded vendor tiers, and SHALL fall back to the static tier
table only when the catalog is unreachable, labelling the estimate source in the policy decision.

#### Scenario: Switch decision uses real pricing

- **WHEN** a vendor limit triggers policy evaluation with the catalog reachable
- **THEN** the cost delta SHALL derive from catalog per-Mtok pricing
- **AND** the decision record SHALL cite `catalog` as the estimate source

### Requirement: Exploration Budget Enforcement in Roadmap Runs

Roadmap orchestration SHALL respect the routing exploration budget: roadmap items dispatched as
exploration SHALL be marked in the learning log, and exploration SHALL be disabled for items whose
policy declares a preferred vendor or fail-closed posture.

#### Scenario: Fail-closed item never explored

- **WHEN** a roadmap item's policy is fail-closed and the resolver would explore
- **THEN** the dispatch SHALL use the exploitation-ranked candidate instead
