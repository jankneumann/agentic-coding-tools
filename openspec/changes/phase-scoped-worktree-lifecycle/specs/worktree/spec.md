## ADDED Requirements

### Requirement: D5 — Registry v2 SHALL Separate Activity Leases from Retention

The managed-worktree registry SHALL use a locked schema-v2 lifecycle contract in
which `retained` and `retention_reason` describe garbage-collection protection
and `activity_lease` describes current write activity. An activity lease MUST
contain an owner identity, phase, reason, acquisition time, last heartbeat, and
expiry. Retention MUST NOT, by itself, be interpreted as current activity.

Every read-modify-write registry operation SHALL hold an inter-process file lock
and SHALL replace the registry atomically so concurrent acquire, renew, release,
retain, teardown, and garbage-collection operations cannot lose updates.

#### Scenario: AC-09 — Retained idle worktree survives GC without blocking sync points

- **WHEN** a registry entry has `retained: true` and no live activity lease
- **AND** the worktree is older than the garbage-collection threshold
- **THEN** garbage collection SHALL preserve the worktree
- **AND** the active-agent guard MUST NOT report the entry as a blocker

#### Scenario: Concurrent lifecycle updates preserve both owners' records

- **WHEN** two processes update different registry entries concurrently
- **THEN** each process SHALL serialize its read-modify-write operation under the registry lock
- **AND** the final valid JSON document SHALL contain both updates

### Requirement: D6 — Activity Lease Operations SHALL Be Owner-Scoped and Crash-Tolerant

The worktree command surface SHALL provide acquire, renew, release, owner/session
release, and status operations for activity leases. Acquire SHALL reject a
different live owner, renew SHALL require the current owner, and release SHALL
remove only the matching owner's lease. Repeating a matching release or safe
teardown SHALL succeed without changing another owner's state.

Unless explicitly configured otherwise, acquisition SHALL create a 30-minute
lease and an active workflow SHALL renew it at intervals no longer than 5
minutes. Expired leases SHALL cease to block sync points. Expiry MUST NOT delete,
reset, clean, or otherwise mutate worktree contents or unmerged branches.

#### Scenario: Owner acquires and renews the default lease

- **WHEN** owner `implement:run-42` acquires an activity lease at time T
- **THEN** the lease SHALL expire at T plus 30 minutes
- **AND** a heartbeat renewal by the same owner at or before T plus 5 minutes SHALL advance `last_heartbeat` and `expires_at`

#### Scenario: Different owner cannot renew or release a live lease

- **WHEN** a live lease is owned by `autopilot:run-a`
- **AND** owner `plan:run-b` requests renew or release
- **THEN** the operation MUST fail with an owner-mismatch result
- **AND** the `autopilot:run-a` lease SHALL remain unchanged

#### Scenario: Matching release is idempotent

- **WHEN** an owner releases its activity lease successfully
- **AND** the same owner repeats the release
- **THEN** the second operation SHALL succeed as an already-released no-op
- **AND** no other entry or retention setting SHALL change

#### Scenario: AC-08 — Lease expiry unblocks without deleting dirty work

- **WHEN** a process crashes after acquiring a lease
- **AND** an injected clock advances beyond the lease's `expires_at`
- **THEN** the active-agent guard SHALL stop reporting that lease as a blocker
- **AND** the worktree, its dirty files, and its unmerged branch MUST remain untouched

### Requirement: Lease Inspection and Recovery SHALL Be Operator-Visible

The worktree tooling SHALL provide read-only status and migration-report output
that distinguishes live activity, expired activity, retention, and legacy
interpretation. It SHALL provide explicit owner-scoped recovery commands for
release and safe teardown. Inspection MUST NOT rewrite registry entries.

#### Scenario: Inspection reports lifecycle categories without mutation

- **WHEN** the registry contains one live lease, one expired lease, one retained-idle entry, and one legacy entry
- **THEN** status SHALL identify each category and its owner or interpretation where applicable
- **AND** the migration report SHALL describe the prospective v1-to-v2 mapping
- **AND** neither command SHALL modify the registry bytes

#### Scenario: Recovery refuses destructive teardown

- **WHEN** an operator requests teardown of a dirty worktree or a worktree with an unmerged branch
- **THEN** the command MUST refuse automatic deletion and report the unsafe condition
- **AND** it SHALL NOT use force to bypass the condition

### Requirement: Registry Migration SHALL Preserve Existing Local Workflow Compatibility

All registry readers SHALL accept schema-v1 and schema-v2 entries. A v1
`pinned: true` value SHALL be interpreted as retention for garbage collection,
not as proof of current activity. During migration only, a fresh legacy
heartbeat MAY provide activity evidence; a stale or absent heartbeat MUST NOT
block a sync point. The `pin` and `unpin` commands SHALL remain compatibility
aliases for retention and SHALL NOT acquire or release activity leases.

Existing local worktree setup, branch override, isolation detection, and package
worktree behavior SHALL otherwise remain compatible.

#### Scenario: AC-11 — Legacy pinned entry remains readable and safe

- **WHEN** a schema-v1 entry has `pinned: true` and a stale heartbeat
- **THEN** the reader SHALL expose it as retained and idle without data loss
- **AND** garbage collection SHALL preserve it
- **AND** the active-agent guard MUST NOT block on it

#### Scenario: Fresh legacy heartbeat is transitional activity evidence

- **WHEN** a schema-v1 entry has a heartbeat inside the documented legacy freshness window
- **THEN** the active-agent guard SHALL report it as transitional active work
- **AND** inspection output SHALL identify that the evidence came from a legacy heartbeat

#### Scenario: Compatibility aliases affect retention only

- **WHEN** the operator invokes `pin` and then `unpin` for a schema-v2 entry
- **THEN** `pin` SHALL set retention and `unpin` SHALL clear retention
- **AND** neither command SHALL create, renew, release, or overwrite `activity_lease`

### Requirement: Activity Lease Commands SHALL Respect Environment Isolation

Every mutating worktree command SHALL continue to use the common environment
detection contract. When harness isolation is provided, local registry and
`.git-worktrees/` mutations, including lease and retention mutations, SHALL be
short-circuited. Read-only inspection SHALL continue to function and SHALL
describe the in-place checkout without claiming a repository-owned live lease.

#### Scenario: Lease mutations short-circuit under harness isolation

- **WHEN** `EnvironmentProfile.detect()` returns `isolation_provided=true`
- **AND** a caller invokes acquire, renew, release, owner/session release, retain, or teardown
- **THEN** the command MUST NOT mutate `.git-worktrees/` or its registry
- **AND** it SHALL exit successfully with an explicit short-circuit message
