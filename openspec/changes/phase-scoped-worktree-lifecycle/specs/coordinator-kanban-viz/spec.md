## MODIFIED Requirements

### Requirement: New Coordinator Endpoint — Worktree Active Projection

The coordinator SHALL expose `GET /worktrees/active` as a projection of the
repository-owned worktree registry. The projection SHALL distinguish `active`
activity leases from `retained` garbage-collection protection and SHALL include,
for a live lease, owner, phase, reason, last heartbeat, and expiry. It SHALL
exclude expired leases from the active set while preserving a retained-idle
entry as non-active status data. The frontend MUST NOT read the registry file
directly.

Schema-v1 entries SHALL remain readable. A legacy `pinned: true` field SHALL be
projected as retained, not automatically active; only a fresh legacy heartbeat
within the documented compatibility window MAY be projected as transitional
activity.

#### Scenario: Live lease is projected as active

- **WHEN** a schema-v2 worktree entry has an unexpired activity lease
- **THEN** `GET /worktrees/active` SHALL include it with `active: true`
- **AND** the response SHALL include its owner, phase, reason, `last_heartbeat`, and `expires_at`

#### Scenario: AC-09 — Retained idle entry is visible but not active

- **WHEN** a schema-v2 entry has `retained: true` and no live activity lease
- **THEN** the worktree projection SHALL expose `retained: true` and `active: false`
- **AND** the sync-point status endpoint MUST NOT count it as a blocker

#### Scenario: AC-08 — Expired lease disappears from active blockers

- **WHEN** an activity lease's `expires_at` is earlier than the coordinator's current time
- **THEN** the active projection SHALL NOT expose it as active
- **AND** sync-point status SHALL NOT count it as a blocker
- **AND** the coordinator MUST NOT delete or clean its worktree

#### Scenario: AC-11 — Legacy pin projects as retention

- **WHEN** the coordinator reads a schema-v1 entry with `pinned: true` and a stale heartbeat
- **THEN** the projection SHALL report retained compatibility state
- **AND** it MUST report `active: false`
- **AND** the endpoint SHALL remain successful without rewriting the registry

## ADDED Requirements

### Requirement: Coordinator Sync-Point Status SHALL Use Live Activity Semantics

The coordinator SHALL expose sync-point blocker status by reusing the canonical
active-agent check. A blocker SHALL be a live schema-v2 activity lease or a
fresh legacy heartbeat during migration. Retention alone and expired activity
MUST NOT block `/cleanup-feature`, `/merge-pull-requests`, or `/update-specs`.
The coordinator MUST NOT duplicate or weaken the local guard's lifecycle logic.

#### Scenario: AC-02 — Released proposal worktree does not block merge triage

- **WHEN** standalone planning has released its owner lease after pushing a proposal PR
- **AND** the worktree is absent or retained-idle
- **THEN** sync-point status SHALL report no blocker for that planning run
- **AND** `/merge-pull-requests` SHALL be clear to start without force

#### Scenario: Live continuous autopilot lease blocks sync points

- **WHEN** an unexpired `autopilot:<run-id>` lease is present
- **THEN** each applicable sync-point status SHALL report the owner as a blocker
- **AND** the response SHALL expose phase and heartbeat age for operator inspection

## ADDED Requirements

### Requirement: Coordinator Merge Views SHALL Preserve Delivery-Stage Evidence

Coordinator APIs and UI consumers that render durable merge plans SHALL carry
the OpenSpec delivery stage independently from PR origin and author vendor. They
SHALL display `proposal`, `implementation`, `mixed`, or `ambiguous` together
with classifier evidence and warnings. An ambiguous result MUST be visibly
blocked from automatic cleanup or archival actions.

#### Scenario: Ambiguous delivery is operator-visible

- **WHEN** a merge-plan record contains `delivery_stage: ambiguous`
- **THEN** the coordinator view SHALL display the changed-file, base-state, and marker conflict evidence
- **AND** automatic cleanup/archive controls MUST remain unavailable until an explicit operator disposition is recorded

#### Scenario: Proposal plan omits archival action

- **WHEN** a merge-plan record contains `delivery_stage: proposal`
- **THEN** the coordinator view SHALL show strict OpenSpec validation and main-context convergence as required actions
- **AND** it MUST NOT show implementation validation, cleanup, or archival as scheduled actions
