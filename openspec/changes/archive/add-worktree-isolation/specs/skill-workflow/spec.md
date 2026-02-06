# Spec Delta: skill-workflow

## ADDED Requirements

### Requirement: Worktree Isolation Pattern

The `implement-feature`, `iterate-on-implementation`, and `cleanup-feature` skills SHALL support per-feature git worktree isolation to enable concurrent CLI sessions working on different features.

Worktrees SHALL be created at `../<repo-name>.worktrees/<change-id>/` relative to the main repository.

#### Scenario: Worktree creation on implement-feature
- **WHEN** the user invokes `/implement-feature <change-id>`
- **THEN** the skill SHALL create a worktree at `../<repo-name>.worktrees/<change-id>/`
- **AND** create the feature branch `openspec/<change-id>` if it doesn't exist
- **AND** change the working directory to the worktree
- **AND** continue implementation in the worktree

#### Scenario: Skip worktree creation when already in worktree
- **WHEN** the user invokes `/implement-feature <change-id>`
- **AND** the current working directory is already the worktree for that change-id
- **THEN** the skill SHALL skip worktree creation
- **AND** continue with implementation

#### Scenario: Worktree detection in iterate-on-implementation
- **WHEN** the user invokes `/iterate-on-implementation <change-id>`
- **AND** the current working directory is a git worktree
- **THEN** the skill SHALL detect the main repository path
- **AND** resolve OpenSpec files from the main repository
- **AND** operate normally on implementation files in the worktree

#### Scenario: Worktree cleanup on cleanup-feature
- **WHEN** the user invokes `/cleanup-feature <change-id>`
- **AND** a worktree exists for that change-id
- **THEN** the skill SHALL remove the worktree after archiving
- **AND** NOT remove the worktree if cleanup is aborted

### Requirement: OpenSpec File Access in Worktrees

Skills running in worktrees SHALL access OpenSpec files from the main repository, not from the worktree.

#### Scenario: OpenSpec path resolution in worktree
- **WHEN** a skill needs to read OpenSpec files (proposal.md, tasks.md, design.md, specs/)
- **AND** the skill is running in a worktree
- **THEN** it SHALL resolve the path relative to the main repository using git-common-dir
- **AND** NOT expect OpenSpec files to exist in the worktree
