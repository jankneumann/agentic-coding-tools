## ADDED Requirements

### Requirement: Approved Roadmap Execution

The supervise skill SHALL expose an execution path that drives an operator-approved roadmap through `execute_roadmap()` using the delegated `dispatch_fn` contract without requiring per-item approval.

#### Scenario: Execute an inherited-approved roadmap
- **WHEN** the operator invokes `/autopilot-roadmap` or approves a roadmap batch from `/supervise`
- **THEN** the supervisor supplies the delegated dispatch callback and exact roadmap item `change_id` values
- **AND** execution continues through ready items without new discovery, direction, or per-item plan questions

#### Scenario: Refuse unapproved roadmap execution
- **WHEN** no durable roadmap-altitude approval can be established
- **THEN** the supervisor does not dispatch an implementation agent
- **AND** it reports the missing approval without mutating roadmap execution state

### Requirement: Background Worktree Isolation

The supervise skill MUST start each delegated Autopilot item as a background sub-agent in a distinct managed worktree and MUST retain only its structured outcome and handoff identifier.

#### Scenario: Run two disjoint changes in parallel
- **WHEN** the delegated batch contains two disjoint changes
- **THEN** the host starts both `/autopilot <change-id>` agents in the background with distinct worktree paths and branches
- **AND** the supervisor context after collection contains both outcomes but no child transcript

#### Scenario: Child dispatch cannot prove isolation
- **WHEN** worktree setup or path/branch verification fails for a selected item
- **THEN** that item returns a failed dispatch outcome before `/autopilot` begins
- **AND** other independently isolated batch members may complete without sharing the failed worktree

#### Scenario: Child parks at a pending gate
- **WHEN** a background Autopilot child reaches a pending gate or policy pause
- **THEN** the host returns a parked result containing the bounded gate or pause snapshot
- **AND** success and parked results include worktree path, branch, and loop-state evidence that exactly match the prepared attempt
- **AND** the supervisor retains the next action without retaining the child transcript or marking the item failed

### Requirement: Router-Neutral Supervisor Dispatch

The supervise skill SHALL pass through router-owned dispatch context and SHALL NOT select or override the vendor, model, location, or cost-policy decision itself.

#### Scenario: Preserve routed context
- **WHEN** the roadmap orchestrator supplies router decision fields in dispatch context
- **THEN** the supervisor forwards those fields unchanged to the background dispatch boundary
- **AND** the recorded result remains correlated to the original dispatch identifier

#### Scenario: Router context is unavailable
- **WHEN** no router decision is present
- **THEN** the supervisor uses the existing archetype/provider resolution path
- **AND** it does not invent a vendor preference or widen the item scope

#### Scenario: Reject unsafe additive context
- **WHEN** dispatch context contains a secret-like or token key, raw response or transcript content, nesting deeper than four levels, or canonical JSON larger than 16 KiB
- **THEN** preparation fails before persistence or dispatch with a bounded deterministic reason
- **AND** valid bounded router-owned fields pass through unchanged
