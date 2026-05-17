## ADDED Requirements

### Requirement: Checkout Policy Helper SHALL Reuse Environment Detection

The worktree infrastructure SHALL expose a checkout mutation policy helper that
reuses `EnvironmentProfile.detect()` to decide whether local worktree isolation
is required.

#### Scenario: Cloud or harness isolation allows in-place mutation

- **WHEN** `EnvironmentProfile.detect()` returns `isolation_provided=true`
- **AND** a mutating skill calls the checkout policy helper
- **THEN** the helper SHALL allow mutation in the current checkout
- **AND** it SHALL report the reason as `isolated_harness`

#### Scenario: Local shared checkout requires worktree

- **WHEN** `EnvironmentProfile.detect()` returns `isolation_provided=false`
- **AND** the current checkout root is not under `.git-worktrees/`
- **AND** the caller is not an approved sync-point
- **THEN** the helper SHALL reject mutation
- **AND** it SHALL exit non-zero when invoked through its CLI

#### Scenario: Local managed worktree allows mutation

- **WHEN** `EnvironmentProfile.detect()` returns `isolation_provided=false`
- **AND** the current checkout root is under `.git-worktrees/`
- **THEN** the helper SHALL allow mutation
- **AND** it SHALL report the reason as `managed_worktree`

#### Scenario: Sync-point allowance is explicit

- **WHEN** `EnvironmentProfile.detect()` returns `isolation_provided=false`
- **AND** the current checkout root is the shared checkout
- **AND** the caller passes `--sync-point`
- **THEN** the helper SHALL allow mutation
- **AND** it SHALL report the reason as `approved_sync_point`
- **AND** it SHALL NOT skip the caller's separate clean-tree or active-agent
  guard requirements
