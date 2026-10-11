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
- **AND** it MUST verify that no active agents hold non-stale worktrees unless
  the operator explicitly uses a force escape hatch

#### Scenario: No sync window declared keeps the user-invoked default

- **WHEN** the trust posture contract is absent, or declares no `sync_windows`
- **AND** a sync-point skill is started by a scheduler or any other non-user
  trigger
- **THEN** the skill MUST refuse to touch main
- **AND** user invocation MUST remain the only path by which the skill runs

#### Scenario: Scheduled invocation names an undeclared window or skill

- **WHEN** a scheduled invocation names a sync window id that the trust posture
  does not declare, or names a window that does not list the invoked skill
- **THEN** the skill MUST refuse to touch main
- **AND** it MUST report which declaration was missing

#### Scenario: Scheduled invocation keeps the guards unchanged

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** it MUST run the same clean-tree check and active-agent guard as a
  user-invoked run
- **AND** it MUST NOT use the force escape hatch, which remains available only
  to an explicit operator
- **AND** when an active agent holds a non-stale worktree it MUST stop without
  touching main

#### Scenario: Scheduled invocation keeps validation gates unchanged

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** every validation gate, CI check, and readiness verdict that a
  user-invoked run requires before merging MUST still be required
- **AND** a PR that fails any of them MUST NOT be merged by the scheduled run

#### Scenario: Scheduled invocation is bounded by the window's sources and ceiling

- **WHEN** a sync-point skill runs as a scheduled invocation under a declared
  sync window
- **THEN** it MUST act only on pull requests whose origin is listed in the
  window's `allowed_sources`
- **AND** it MUST NOT merge unattended a pull request whose kind exceeds the
  window's `auto_merge_ceiling`
- **AND** a window whose `auto_merge_ceiling` is `none` MUST NOT merge any pull
  request unattended
