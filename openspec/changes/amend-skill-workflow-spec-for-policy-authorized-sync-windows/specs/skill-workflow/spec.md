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
- **AND** a scheduler or any other non-user trigger would start a sync-point
  skill
- **THEN** the trigger MUST NOT start the skill without naming a sync window id
- **AND** a skill started with a sync window id MUST call the trust posture
  sync-window authorization check before touching main, and MUST refuse to
  touch main when that check fails
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
- **AND** every trust posture gate disposition that applies to the same action
  (including the `merge` gate) MUST still be evaluated as it would be for that
  action without a window
- **AND** a gate that resolves to `block` MUST stop the scheduled run's action

### Requirement: Merge Conductor Invokes Iterate Skills

`/merge-pull-requests` in its default plan-then-execute path SHALL be allowed to
invoke `/iterate-on-plan` and `/iterate-on-implementation` as remediations for
open pull requests. Those invocations SHALL run in the iterate skill's managed
feature worktree and SHALL NOT write `main`. The merge skill remains the
sync-point for merges into `main`: it is user-invoked by default, or runs as a
scheduled invocation only under a declared sync window as defined by "Main
Receives Work Through PR Sync Points".

<!-- Scenario ID: skill-workflow.merge-invokes-iterate -->
#### Scenario: Merge-triggered iterate writes the feature branch only

- **WHEN** `/merge-pull-requests` invokes `/iterate-on-plan` or `/iterate-on-implementation` for a node
- **THEN** iterate SHALL enter or create the change's managed worktree before any mutation
- **AND** SHALL commit on the feature branch
- **AND** SHALL NOT commit to local `main`

<!-- Scenario ID: skill-workflow.merge-still-sync-point -->
#### Scenario: Merge remains the only main writer in the loop

- **WHEN** iterate returns and the node is mergeable
- **THEN** only `/merge-pull-requests` SHALL merge into `main`
- **AND** iterate SHALL NOT call `gh pr merge` or otherwise land the PR

#### Scenario: Scheduled merge conductor keeps iterate on the feature branch

- **WHEN** `/merge-pull-requests` runs as a scheduled invocation under a
  declared sync window and invokes `/iterate-on-plan` or
  `/iterate-on-implementation` for a node
- **THEN** iterate SHALL still commit only on the feature branch
- **AND** only the merge skill SHALL merge into `main`, subject to the window's
  `allowed_sources` and `auto_merge_ceiling`
