## MODIFIED Requirements

### Requirement: Main Receives Work Through PR Sync Points

The system SHALL route completed local CLI work to main through PR sync points.
In local CLI execution, completed planning, implementation, fix, validation, and
artifact-generation work MUST reach main only through PR review followed by an
explicit sync-point operation.

A sync-point operation SHALL be explicitly user-invoked by default. A sync-point
skill MAY instead run as a scheduled invocation only under a sync window that the
repository's trust posture contract (`TRUST_POSTURE.md`, `sync_windows`) explicitly
declares and that lists that skill. A scheduled invocation SHALL NOT relax the
clean-tree check, the active-agent guard, or any validation gate.

The active-agent guard SHALL be scoped to the work the sync-point operation is
about to perform. An active worktree is one whose registry entry is pinned or
whose last heartbeat is within the stale threshold. An active worktree
*overlaps* an operation when its branch is one the operation will merge or
rewrite, or when its change id is one the operation will archive, clean up, or
write specs for. The guard mode is read from the trust posture contract
(`sync_point.active_agent_guard`) and defaults to `overlap`; `repo-wide`
restores blocking on any active worktree, and `off` skips the worktree check
for user-invoked runs only. Every guard result MUST report the mode and the
scope it applied.

#### Scenario: Plan refinement completes

- **WHEN** `/iterate-on-plan` updates proposal, design, task, contract, or spec
  artifacts
- **THEN** it MUST commit those updates on the feature branch in a worktree
- **AND** it MUST NOT commit directly to local main

#### Scenario: Sync-point skill touches main

- **WHEN** `/merge-pull-requests`, `/update-specs`, or the main-touching portion
  of `/cleanup-feature` modifies the shared checkout
- **THEN** the skill MUST be explicitly user-invoked, or run as a scheduled
  invocation authorized by a declared sync window
- **AND** it MUST verify a clean working tree
- **AND** it MUST verify that no active agent holds a non-stale worktree that
  overlaps the operation, unless the operator explicitly uses a force escape
  hatch

#### Scenario: Active worktree on an unrelated branch does not block a merge

- **WHEN** the guard mode is `overlap`
- **AND** the only active worktrees are registered on branches other than the
  one being merged and for changes other than the ones being archived
- **THEN** the sync-point operation MUST proceed without a force escape hatch
- **AND** the guard result MUST name the mode and the branches and change ids
  it checked

#### Scenario: Active worktree on the merged branch blocks

- **WHEN** the guard mode is `overlap`
- **AND** an active worktree is registered on the branch the operation is about
  to merge
- **THEN** the operation MUST stop without touching main
- **AND** the reason MUST name that worktree's change id, agent id when
  present, and branch

#### Scenario: Active worktree for the archived change blocks cleanup

- **WHEN** the guard mode is `overlap`
- **AND** an active worktree is registered for a change whose directory the
  operation is about to archive or whose specs it is about to write
- **THEN** the operation MUST stop without touching that change
- **AND** operations on other changes in the same run MAY proceed

#### Scenario: Repo-wide mode restores blocking on any active worktree

- **WHEN** the trust posture declares `sync_point.active_agent_guard: repo-wide`
- **AND** any active worktree exists, whether or not it overlaps
- **THEN** the sync-point operation MUST stop without touching main

#### Scenario: Off mode is honoured only for user-invoked runs

- **WHEN** the trust posture declares `sync_point.active_agent_guard: off`
- **AND** the sync-point skill is explicitly user-invoked
- **THEN** the worktree check MUST be skipped and the guard result MUST record
  mode `off`
- **AND** the coordinator lock check MUST still run

#### Scenario: Scheduled invocation never runs with the guard off

- **WHEN** the trust posture declares `sync_point.active_agent_guard: off`
- **AND** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** the guard MUST run in `overlap` mode
- **AND** an active worktree that overlaps MUST stop the run without touching
  main

#### Scenario: Guard cannot determine its scope

- **WHEN** a kernel call site cannot determine the branch it is about to merge
  or the changes it is about to archive
- **THEN** it MUST run the guard in `repo-wide` mode for that operation
- **AND** it MUST record why the scope could not be determined

#### Scenario: Scheduled invocation names a window and passes authorization first

- **WHEN** a scheduler or any other non-user trigger starts a sync-point skill
- **THEN** the trigger MUST name a sync window id, and MUST NOT start the skill
  without one
- **AND** the skill MUST call the trust posture sync-window authorization check
  before any other work, including PR discovery, remediation, branch writes, or
  any other externally visible side effect
- **AND** when that check fails the skill MUST stop without performing any of
  that work and without touching main
- **AND** the trigger MUST start the skill only at times the window's declared
  `cadence` permits; computing fire times and their tolerance is the
  scheduler's responsibility

#### Scenario: No sync window declared keeps the user-invoked default

- **WHEN** the trust posture contract is absent, or declares no `sync_windows`
- **AND** a scheduler or any other non-user trigger starts a sync-point skill
- **THEN** the sync-window authorization check MUST fail for every window id
- **AND** the skill MUST stop without touching main
- **AND** user invocation MUST remain the only path by which the skill can
  touch main

#### Scenario: Scheduled invocation names an undeclared window or skill

- **WHEN** a scheduled invocation names a sync window id that the trust posture
  does not declare, or names a window that does not list the invoked skill
- **THEN** the skill MUST refuse to touch main
- **AND** it MUST report which declaration was missing

#### Scenario: Scheduled invocation keeps the guards unchanged

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** it MUST run the same clean-tree check and active-agent guard, in the
  same scope, as a user-invoked run
- **AND** it MUST NOT use the force escape hatch, which remains available only
  to an explicit operator
- **AND** when an active agent holds a non-stale worktree that overlaps the
  operation it MUST stop without touching main

#### Scenario: Scheduled invocation keeps validation gates unchanged

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** every validation gate, CI check, and readiness verdict that a
  user-invoked run requires before merging MUST still be required
- **AND** a PR that fails any of them MUST NOT be merged by the scheduled run

#### Scenario: Scheduled invocation is bounded by the window's sources and ceiling

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** whenever it selects, remediates, or merges pull requests, it MUST
  act only on pull requests whose origin is listed in the window's
  `allowed_sources`
- **AND** it MUST NOT merge unattended a pull request whose kind exceeds the
  window's `auto_merge_ceiling`, or whose kind cannot be classified
- **AND** a window whose `auto_merge_ceiling` is `none` MUST NOT merge any pull
  request unattended

#### Scenario: Sync window does not override gate dispositions

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** the window's authorization MUST be treated as necessary but not
  sufficient
- **AND** the window MUST NOT change any trust posture gate disposition; every
  gate that applies to the scheduled action MUST be evaluated exactly as it
  would be without the window
- **AND** a gate that resolves to `block` MUST stop the scheduled run's action
- **AND** which gates apply to a scheduled sync-point action is defined by the
  change that adds that scheduled caller (`ri-12` headless merge, `ri-13`
  drain); this requirement defines no new gate applicability
