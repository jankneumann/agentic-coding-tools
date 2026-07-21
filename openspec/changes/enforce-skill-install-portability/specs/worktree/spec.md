## ADDED Requirements

### Requirement: Installed Worktree Helper Discovery

The worktree skill SHALL locate its bootstrap script and sibling helpers from the worktree skill's installed directory. It MUST support canonical `skills/`, `.claude/skills/`, and `.agents/skills/` layouts without requiring a consumer repo-root `skills/` directory.

#### Scenario: Consumer worktree is bootstrapped
- **WHEN** installed `worktree.py setup` creates a worktree from `.claude/skills/worktree` or `.agents/skills/worktree`
- **THEN** it SHALL invoke the co-installed `scripts/worktree-bootstrap.sh`
- **AND** report `BOOTSTRAPPED=true` when bootstrap succeeds

#### Scenario: Installed bootstrap script is absent
- **WHEN** the expected co-installed bootstrap script does not exist
- **THEN** setup SHALL emit an actionable warning and continue with `BOOTSTRAPPED=false`
- **AND** SHALL NOT search only `<consumer>/skills/worktree/scripts`
