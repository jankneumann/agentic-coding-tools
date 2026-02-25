# Spec Delta: skill-workflow

## MODIFIED Requirements

### Requirement: Worktree Isolation Pattern

The `implement-feature`, `iterate-on-implementation`, `cleanup-feature`, and `fix-scrub` skills SHALL support per-feature git worktree isolation to enable concurrent CLI sessions working on different features.

Worktrees SHALL be created at `.git-worktrees/<change-id>/` inside the project root (gitignored), instead of `../<repo-name>.worktrees/<change-id>/`.

Skills that create, remove, or detect worktrees SHALL use `scripts/worktree.py` instead of inline bash commands. The script SHALL use only Python standard library modules and SHALL be invokable via `python3 scripts/worktree.py <subcommand>`, matching the pre-approved `Bash(python3:*)` permission pattern.

#### Scenario: Worktree creation on implement-feature
- **WHEN** the user invokes `/implement-feature <change-id>`
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py setup <change-id>`
- **AND** the worktree SHALL be created at `<project-root>/.git-worktrees/<change-id>/`
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
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py detect`
- **AND** resolve OpenSpec files from the main repository
- **AND** operate normally on implementation files in the worktree

#### Scenario: Worktree cleanup on cleanup-feature
- **WHEN** the user invokes `/cleanup-feature <change-id>`
- **AND** a worktree exists for that change-id
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py teardown <change-id>`
- **AND** the teardown SHALL check both `.git-worktrees/` and legacy `../<repo>.worktrees/` locations
- **AND** NOT remove the worktree if cleanup is aborted

### Requirement: Fix Scrub Optional Worktree Isolation

The fix-scrub skill SHALL support optional git worktree isolation using the same pattern as implement-feature, enabled via `--worktree` flag or auto-detected when an active implementation worktree exists.

#### Scenario: Explicit worktree creation with --worktree flag
- **WHEN** the user invokes `/fix-scrub --worktree`
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py setup <date> --branch <name> --prefix fix-scrub`
- **AND** the worktree SHALL be created at `<project-root>/.git-worktrees/fix-scrub/<date>/`
- **AND** change the working directory to the worktree

#### Scenario: Auto-detect active implementation worktree
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is inside a git worktree (detected via `python3 scripts/worktree.py detect`)
- **THEN** the skill SHALL create a separate worktree for the fix-scrub branch
- **AND** NOT apply fixes in the active implementation worktree

#### Scenario: Worktree not needed
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is the main repository (not a worktree)
- **THEN** the skill SHALL create only a branch (no worktree)
- **AND** apply fixes on the branch in the main working tree

#### Scenario: Skip worktree creation when already in fix-scrub worktree
- **WHEN** the user invokes `/fix-scrub`
- **AND** the current working directory is already a fix-scrub worktree
- **THEN** the skill SHALL skip worktree creation
- **AND** continue applying fixes in the existing worktree

## ADDED Requirements

### Requirement: Gitignore Worktree Directory

The project `.gitignore` SHALL include `.git-worktrees/` to prevent worktree contents from being tracked by the main repository.

#### Scenario: Worktree contents not tracked
- **WHEN** a worktree exists at `.git-worktrees/<change-id>/`
- **AND** the user runs `git status` in the main repo
- **THEN** files inside `.git-worktrees/` SHALL NOT appear as untracked
