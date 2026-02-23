## ADDED Requirements

### Requirement: Fix Scrub Branch Isolation

The fix-scrub skill SHALL create an isolated branch before applying any code changes, ensuring all fixes go through PR review before reaching main.

#### Scenario: Branch creation on fix-scrub invocation
- **WHEN** the user invokes `/fix-scrub`
- **THEN** the skill SHALL create a branch named `fix-scrub/<YYYY-MM-DD>` from the current main HEAD
- **AND** switch to the new branch before applying any fixes
- **AND** NOT apply changes directly to main

#### Scenario: Branch name collision with existing branch
- **WHEN** the user invokes `/fix-scrub` and a branch `fix-scrub/<YYYY-MM-DD>` already exists
- **THEN** the skill SHALL append a numeric suffix (e.g., `fix-scrub/2026-02-22-2`)
- **AND** create the branch with the suffixed name

#### Scenario: PR creation after fixes applied
- **WHEN** fix-scrub has applied fixes and quality checks pass (or user approves despite warnings)
- **THEN** the skill SHALL push the branch to origin
- **AND** create a PR with the fix-scrub-report summary as the body
- **AND** present the PR URL to the user

#### Scenario: No fixes applied
- **WHEN** fix-scrub classifies all findings as manual-only or dry-run mode is active
- **THEN** the skill SHALL NOT create a branch or PR
- **AND** report the classification results without git operations

### Requirement: Fix Scrub Optional Worktree Isolation

The fix-scrub skill SHALL support optional git worktree isolation using the same pattern as implement-feature, enabled via `--worktree` flag or auto-detected when an active implementation worktree exists.

#### Scenario: Explicit worktree creation with --worktree flag
- **WHEN** the user invokes `/fix-scrub --worktree`
- **THEN** the skill SHALL create a worktree at `../<repo-name>.worktrees/fix-scrub/<date>/`
- **AND** create the fix-scrub branch in the worktree
- **AND** change the working directory to the worktree

#### Scenario: Auto-detect active implementation worktree
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is inside a git worktree (detected via `git rev-parse --git-common-dir`)
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

### Requirement: Skill Script Path Resolution Convention

All SKILL.md files that reference co-located Python scripts SHALL use the `<agent-skills-dir>` placeholder convention to enable portable script resolution across agent runtimes.

Scripts are authored in `skills/<name>/scripts/` and distributed by `install.sh` to agent config directories (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`). Agents execute scripts from their own config directory, not from the `skills/` source.

#### Scenario: Script path placeholder in SKILL.md
- **WHEN** a SKILL.md contains a bash code block that invokes a Python script
- **THEN** the script path SHALL use the `<agent-skills-dir>/<skill-name>/scripts/` placeholder pattern
- **AND** the agent runtime SHALL substitute `<agent-skills-dir>` with its own config directory path (e.g., `.claude/skills`, `.codex/skills`, `.gemini/skills`)

#### Scenario: Agent substitution for Claude
- **WHEN** Claude Code reads a SKILL.md containing `python3 <agent-skills-dir>/fix-scrub/scripts/main.py`
- **THEN** it SHALL execute `python3 .claude/skills/fix-scrub/scripts/main.py`

#### Scenario: Agent substitution for Codex and Gemini
- **WHEN** Codex or Gemini reads a SKILL.md containing the `<agent-skills-dir>` placeholder
- **THEN** it SHALL substitute with `.codex/skills` or `.gemini/skills` respectively

#### Scenario: Script not found at agent config path
- **WHEN** the agent substitutes the placeholder and the resolved script path does not exist
- **THEN** the agent SHALL report an error indicating the script is missing
- **AND** suggest running `skills/install.sh` to sync scripts to agent directories

#### Scenario: Convention documented in SKILL.md
- **WHEN** a SKILL.md uses the `<agent-skills-dir>` placeholder
- **THEN** it SHALL include a "Script Location" note explaining the convention and the substitution rule

## MODIFIED Requirements

### Requirement: Fix Scrub Commit Convention (MODIFIED)

The fix-scrub skill SHALL commit all applied fixes as a single commit with a structured message on the fix-scrub branch (not main).

#### Scenario: Commit on fix-scrub branch
- **WHEN** fixes have been applied and quality checks pass (or the user approves despite warnings)
- **THEN** the skill SHALL stage all changed files and commit on the `fix-scrub/<date>` branch
- **AND** use the existing commit message format
- **AND** NOT commit to main directly
