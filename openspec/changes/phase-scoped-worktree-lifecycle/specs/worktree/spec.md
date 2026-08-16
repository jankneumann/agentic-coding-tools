## ADDED Requirements

### Requirement: Registry v2 SHALL Separate Activity Leases from Retention

The managed-worktree registry SHALL use a locked schema-v2 lifecycle contract in
which `retained` and `retention_reason` describe garbage-collection protection
and `activity_lease` describes current write activity. An activity lease MUST
contain an owner identity, phase, reason, acquisition time, last heartbeat, and
expiry, plus a single-acquisition `lease_id`, per-process
`controller_instance_id`, nullable `session_id`, lifecycle mode, and TTL. Each
entry SHALL carry an `entry_generation` and exact
durability target; package entries target the parent feature ref. Retention MUST
NOT, by itself, be interpreted as current activity.
Entries with preserved dirty or non-durable work SHALL expose
`recovery_required` independently from activity and retention.

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

### Requirement: Activity Lease Operations SHALL Be Fenced and Crash-Tolerant

The worktree command surface SHALL provide acquire, resume, assert-owned, renew, release,
owner/session release, and status operations for activity leases. Acquire SHALL
reject a different live owner, fencing token, or controller, renew SHALL require
the current ownership triple, and release SHALL remove only that exact lease. Releasing
an absent lease or repeating safe teardown SHALL succeed as a no-op without
attesting prior ownership or changing another owner's state. Replacing an
expired or pre-existing unleased entry SHALL require a new lease/controller
plus an assessment of checkout/submodule cleanliness, stored-target
reachability, and remaining
process evidence; unsafe or indeterminate state SHALL enter recovery quarantine
instead of ordinary acquisition. Remote refresh SHALL occur outside the global
registry lock; the locked mutation SHALL revalidate entry generation and target.
Fresh automatic setup SHALL publish the entry, process evidence, and initial
lease atomically; no separately visible unleased entry may bypass adoption checks. Every
mutation, integration, commit, push, and automatic teardown boundary SHALL
assert the live matching owner, lease id, and controller instance.

Unless explicitly configured otherwise, acquisition SHALL create a 30-minute
lease and an active workflow SHALL renew it at intervals no longer than 5
minutes. Expired leases SHALL cease to block sync points. Expiry MUST NOT delete,
reset, clean, or otherwise mutate worktree contents or unmerged branches.

#### Scenario: Owner acquires and renews the default lease

- **WHEN** owner `phase:IMPLEMENT:run-42` and controller `controller-a` use atomic setup-and-acquire at time T
- **THEN** the lease SHALL expire at T plus 30 minutes
- **AND** a heartbeat renewal by the same ownership triple at or before T plus 5 minutes SHALL advance `last_heartbeat` and `expires_at`

#### Scenario: Different owner cannot renew or release a live lease

- **WHEN** a live lease is owned by `autopilot:run-a`
- **AND** owner `phase:PLAN:run-b` requests renew or release
- **THEN** the operation MUST fail with an owner-mismatch result
- **AND** the `autopilot:run-a` lease SHALL remain unchanged

#### Scenario: Duplicate live controller cannot reuse the same fence

- **WHEN** `controller-a` holds a live lease for an owner and lease id
- **AND** `controller-b` retries acquire, renew, assert, or release with that owner and lease id
- **THEN** every operation from `controller-b` MUST fail without mutation
- **AND** an exact retry from `controller-a` MAY succeed idempotently

#### Scenario: Expired writer is fenced after same-owner resume

- **WHEN** a process holding owner `autopilot:run-a` and lease id `lease-old` expires
- **AND** a replacement controller proves the old evidence stale and safely resumes the same owner with lease id `lease-new`
- **THEN** renew, mutation-boundary assertion, release, and teardown using `lease-old` MUST fail
- **AND** only `lease-new` MAY proceed to integrate, commit, or push

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

#### Scenario: Pre-existing unleased state is not silently adopted

- **WHEN** acquire finds any separately visible unleased entry, including a normalized v1 entry
- **THEN** it SHALL run the complete durability, cleanliness, and prior-process assessment
- **AND** missing durability or indeterminate evidence SHALL quarantine the entry

#### Scenario: Expired takeover quarantines live or unknown process evidence

- **WHEN** an expired lease remains attached to a dirty or non-durable checkout, an exact same-host PID/start-token match, or missing, unreadable, unsupported, or cross-host process evidence
- **AND** a later phase attempts ordinary acquisition
- **THEN** remote refresh SHALL run outside the lifecycle lock and the assessment SHALL revalidate its generation and stored target while holding the lock
- **AND** it SHALL set `recovery_required` and refuse acquisition
- **AND** only explicit operator adoption MAY make the checkout writable again

#### Scenario: Process evidence is collision-safe across entries

- **WHEN** two registry entries intentionally use the same lease id
- **THEN** their evidence paths SHALL differ because the digest includes the canonical entry identity
- **AND** releasing or disposing one entry MUST NOT read or remove the other's evidence

#### Scenario: Clean durable expired takeover uses a new fence

- **WHEN** an expired checkout is proven clean, submodule-clean, reachable from its stored durability target, and its same-host PID is absent or has a different process-start token
- **THEN** resume MAY replace the expired lease with a new lease and controller id
- **AND** the old owner and lease id MUST remain fenced from every later mutation boundary

#### Scenario: PID reuse is stale rather than live evidence

- **WHEN** an expired lease's evidence names a PID that exists on the same host with a different process-start token
- **THEN** takeover SHALL treat that evidence as stale PID reuse rather than the old writer
- **AND** takeover MAY proceed only if every checkout and durability check also passes

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

- **WHEN** an operator requests teardown of a dirty worktree, dirty submodule, or a HEAD not reachable from the stored durability target
- **THEN** the command MUST refuse automatic deletion and report the unsafe condition
- **AND** dirty submodules SHALL be detected before any destructive deinitialization
- **AND** it SHALL NOT use force to bypass the condition

#### Scenario: Pushed proposal branch is safely disposable before merge

- **WHEN** a clean proposal worktree HEAD is reachable from its stored durability target
- **AND** the proposal branch has not been merged into `main`
- **THEN** ownership-triple-checked automatic teardown MAY remove the local worktree
- **AND** being unmerged into `main` MUST NOT by itself be treated as data loss

#### Scenario: Unsafe finalization quarantines recovery state

- **WHEN** phase finalization cannot dispose a dirty or non-durable worktree
- **THEN** it SHALL atomically mark `recovery_required` with a non-empty reason before releasing the lease
- **AND** a later ordinary acquire MUST fail until explicit operator adoption clears the quarantine

#### Scenario: Acquire cannot race owner-checked disposal

- **WHEN** one process begins automatic disposal with a live matching owner and lease id
- **AND** another process attempts acquisition for the same registry entry
- **THEN** the disposer SHALL hold the exclusive lifecycle lock through safety checks, Git removal, and registry removal
- **AND** the acquire SHALL observe either the pre-disposal live lease or the completed removal, never an unfenced worktree being removed

#### Scenario: Teardown reconciles a crash after Git removal

- **WHEN** Git worktree removal succeeds but the process crashes before the exact owner/lease registry entry is deleted
- **THEN** repeated teardown with that owner and lease id SHALL remove the orphan entry and matching process evidence
- **AND** a different owner or lease id MUST remain a non-mutating conflict

#### Scenario: Bulk owner release quarantines preserved checkouts

- **WHEN** recovery release targets every lease with one exact owner
- **THEN** each matching checkout still present SHALL enter `recovery_required` before its lease is cleared
- **AND** no preserved checkout SHALL become eligible for ordinary acquisition

#### Scenario: Explicit recovery adoption populates a complete manual lease

- **WHEN** an operator proves the prior controller's exact process evidence stale and adopts a quarantined entry with a new owner, lease id, controller id, and non-empty reason
- **THEN** the command SHALL clear recovery state and atomically create a schema-valid manual `RECOVERY` lease with nullable session, timestamps, and TTL
- **AND** live or indeterminate prior-process evidence SHALL fail without mutation
- **AND** missing or cross-host evidence SHALL require the separately named audited force-adopt command with actor, rationale, and explicit termination confirmation

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

#### Scenario: Fresh legacy heartbeat maps every canonical lease field

- **WHEN** a fresh schema-v1 heartbeat is normalized or renewed through the compatibility alias
- **THEN** the synthetic v2 lease SHALL contain the deterministic legacy owner and lease id, null session, `LEGACY` phase, migration reason, manual mode, acquisition and heartbeat timestamps, one-hour expiry, and `ttl_seconds: 3600`
- **AND** a later heartbeat against the v2 entry SHALL require that explicit owner and lease id

#### Scenario: Missing or invalid legacy heartbeat is diagnosable and idle

- **WHEN** a schema-v1 entry has no `last_heartbeat` or has an unparsable value
- **THEN** migration inspection SHALL preserve the source value under extensions and report a diagnostic
- **AND** the entry MUST NOT be treated as live activity solely because it is pinned

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

#### Scenario: Corrupt registry blocks safety decisions without rewrite

- **WHEN** the registry is malformed or fails schema validation
- **THEN** mutating lifecycle commands SHALL exit with the documented corrupt-registry result and preserve the file bytes
- **AND** local and coordinator sync-point checks SHALL report an indeterminate blocker
- **AND** continuation SHALL require the existing explicit operator override rather than failing open
