## ADDED Requirements

### Requirement: Local CLI Mutations Require Worktree Isolation

The system SHALL enforce local CLI worktree isolation for repository mutations.
In local CLI execution, every skill phase that creates, modifies, deletes,
formats, commits, pushes, or otherwise mutates repository files or git state
MUST run inside a managed worktree unless it is an explicit sync-point
operation.

#### Scenario: Mutating skill starts from shared checkout

- **WHEN** a local CLI caller invokes a mutating skill from the shared checkout
- **THEN** the skill MUST call `worktree.py setup` before its first write-capable
  step
- **AND** subsequent file writes, generated artifacts, commits, and pushes MUST
  occur inside the resolved worktree
- **AND** the shared checkout outside `.git-worktrees/` MUST remain unchanged

#### Scenario: Mutating skill starts from managed worktree

- **WHEN** a local CLI caller invokes a mutating skill from inside the matching
  managed worktree
- **THEN** the skill MAY continue in that worktree
- **AND** it MUST NOT switch back to the shared checkout for writes

#### Scenario: Isolated harness execution

- **WHEN** `EnvironmentProfile.detect()` reports `isolation_provided=true`
- **THEN** a mutating skill MAY write in the current checkout
- **AND** it MUST NOT create redundant local `.git-worktrees/` state only to
  satisfy the local CLI invariant

### Requirement: Shared Checkout Mutation Policy Guard

The shared skill runtime SHALL provide a reusable checkout mutation policy guard
that mutating skills and scripts can call before writing.

#### Scenario: Local shared checkout is blocked

- **WHEN** `AGENT_EXECUTION_ENV=local` or default local detection applies
- **AND** the current checkout root is not under `.git-worktrees/`
- **AND** the caller does not declare an approved sync-point
- **THEN** the checkout policy guard MUST reject mutation
- **AND** it MUST return a message instructing the caller to enter a managed
  worktree or use a sync-point skill

#### Scenario: Managed worktree is allowed

- **WHEN** local detection applies
- **AND** the current checkout root is under `.git-worktrees/`
- **THEN** the checkout policy guard MUST allow mutation
- **AND** it MUST report the reason as `managed_worktree`

#### Scenario: Sync-point requires explicit declaration

- **WHEN** local detection applies
- **AND** the current checkout is the shared checkout
- **AND** the caller declares `sync_point=true`
- **THEN** the checkout policy guard MAY allow mutation
- **AND** it MUST report the reason as `approved_sync_point`
- **AND** the sync-point skill MUST still run clean-tree and active-agent checks

### Requirement: Artifact-Producing Exploration Uses Worktrees

The `explore-feature` skill MUST distinguish read-only conversational
exploration from artifact-producing exploration.

#### Scenario: Read-only exploration

- **WHEN** `/explore-feature` only reads repository state and returns a
  recommendation in chat
- **THEN** it MAY run from the shared checkout
- **AND** it MUST NOT write files, refresh generated artifacts, create proposals,
  seed coordinator issues, or update issue state

#### Scenario: Artifact-producing exploration

- **WHEN** `/explore-feature` will write `opportunities.json`, refresh
  architecture artifacts, create OpenSpec changes, update docs, seed coordinator
  issues, or persist any other repository artifact
- **THEN** it MUST first enter a managed worktree in local CLI execution
- **AND** it MUST commit and push those artifacts on a feature branch rather than
  writing them to local main

### Requirement: Autopilot Write-Capable Phases Use Worktree Isolation

Autopilot SHALL dispatch every write-capable phase with worktree isolation in
local CLI execution.

#### Scenario: Planning phase writes artifacts

- **WHEN** autopilot runs `PLAN`, `PLAN_ITERATE`, `PLAN_FIX`, or a
  checkpoint-writing `PLAN_REVIEW`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** plan artifacts MUST land on the feature branch

#### Scenario: Implementation phase writes artifacts

- **WHEN** autopilot runs `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX`, or a
  checkpoint-writing `IMPL_REVIEW`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** implementation artifacts MUST land on the feature branch

#### Scenario: Validation phase writes artifacts

- **WHEN** autopilot runs `VALIDATE`, `VAL_FIX`, or an artifact-writing
  `VAL_REVIEW`
- **THEN** validation reports, evidence, and fixes MUST be written in a managed
  worktree or isolated harness checkout
- **AND** those artifacts MUST be reviewable in the PR

### Requirement: Quick Tasks Are Read-Only Unless Isolated

The `quick-task` skill MUST NOT run read-write vendor work against the shared
checkout in local CLI execution.

#### Scenario: Quick task has no write isolation

- **WHEN** a quick task is dispatched from the shared checkout in local CLI
  execution
- **THEN** the task MUST be read-only
- **AND** the vendor prompt MUST forbid file writes, commits, pushes, and
  generated artifacts

#### Scenario: Quick task needs writes

- **WHEN** the operator requests a quick task that may modify files
- **THEN** the skill MUST create or enter a managed worktree first
- **AND** the task MUST push changes on a branch for PR review

### Requirement: Main Receives Work Through PR Sync Points

The system SHALL route completed local CLI work to main through PR sync points.
In local CLI execution, completed planning, implementation, fix, validation, and
artifact-generation work MUST reach main only through PR review followed by an
explicit sync-point operation.

#### Scenario: Plan refinement completes

- **WHEN** `/iterate-on-plan` updates proposal, design, task, contract, or spec
  artifacts
- **THEN** it MUST commit those updates on the feature branch in a worktree
- **AND** it MUST NOT commit directly to local main

#### Scenario: Sync-point skill touches main

- **WHEN** `/merge-pull-requests`, `/update-specs`, or the main-touching portion
  of `/cleanup-feature` modifies the shared checkout
- **THEN** the skill MUST be explicitly user-invoked
- **AND** it MUST verify a clean working tree
- **AND** it MUST verify that no active agents hold non-stale worktrees unless
  the operator explicitly uses a force escape hatch
