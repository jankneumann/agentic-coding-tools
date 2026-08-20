## MODIFIED Requirements

### Requirement: The isolation vocabulary SHALL be closed, two-axis, and pinned once

The isolation contract SHALL carry two axes with closed vocabularies —
`location: local | cloud` and `isolation: none | worktree | sandbox | container` —
validated wherever a routing decision is produced or consumed. `container` SHALL be
admitted while the contract is first pinned (coordinated with
`pin-isolation-contract`), even though its local backend is deferred, so the
contract is not re-opened later.

#### Scenario: Routing decisions validate against the closed vocabulary

- **WHEN** a routing decision is produced or a dispatch consumes one
- **THEN** its `location` and `isolation` values SHALL be validated against the
  closed vocabularies
- **AND** the effective isolation SHALL resolve per `(agent_type, dispatch_mode)`
  through the pinned precedence ladder (router → `get_agent_isolation()` → `none`).

#### Scenario: Unknown values fail structurally

- **WHEN** a routing decision or `agents.yaml` entry carries a value outside the
  closed vocabulary
- **THEN** validation SHALL fail with a structured error naming the field and value
- **AND** the dispatch SHALL NOT proceed under a silently substituted default.
