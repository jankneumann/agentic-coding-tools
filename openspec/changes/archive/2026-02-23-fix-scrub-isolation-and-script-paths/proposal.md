# Change: fix-scrub-isolation-and-script-paths

## Why

The fix-scrub skill currently applies code changes directly to whatever branch is active, with no review gate before landing. Every other code-modifying skill (implement-feature, iterate-on-implementation) uses branch isolation with PR review, making fix-scrub the only skill that can silently land changes on main. This creates risk of regressions reaching main without review.

Separately, all four skills with Python scripts (bug-scrub, fix-scrub, security-review, merge-pull-requests) reference scripts via repo-root-relative paths like `python3 skills/<name>/scripts/main.py`. Agents read SKILL.md from their config directory (e.g., `.claude/skills/<name>/SKILL.md`) where install.sh syncs a co-located copy of the scripts. The mismatch forces agents to infer the correct path, causing initial discovery failures — especially in worktree contexts where the repo root differs.

## What Changes

### Branch isolation for fix-scrub

- Fix-scrub SHALL create a `fix-scrub/<date-or-report-id>` branch from main before applying any fixes
- Fix-scrub SHALL optionally create a git worktree (when `--worktree` flag is passed or when an active implementation worktree is detected) using the same pattern as implement-feature
- Fix-scrub SHALL push the branch and create a PR after applying fixes, using the fix-scrub-report as the PR body
- Fix-scrub SHALL NOT commit directly to main
- The fix-scrub SKILL.md SHALL include the worktree detection and branch setup logic adapted from implement-feature

### Script path discoverability

- All SKILL.md files with script references SHALL use the `<agent-skills-dir>` placeholder convention instead of repo-root-relative paths
- Script invocations SHALL use `python3 <agent-skills-dir>/<skill-name>/scripts/main.py` — the agent runtime substitutes the placeholder with its config directory (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`)
- The convention SHALL be documented in each affected SKILL.md with a "Script Location" note explaining the substitution
- Affected SKILL.md files: bug-scrub, fix-scrub, security-review, merge-pull-requests

## Impact

### Affected specs

- `skill-workflow` — delta spec adding fix-scrub isolation requirements and script path resolution convention

### Code touchpoints

- `skills/fix-scrub/SKILL.md` — add branch/worktree setup step, update script paths
- `skills/bug-scrub/SKILL.md` — update script paths
- `skills/security-review/SKILL.md` — update script paths
- `skills/merge-pull-requests/SKILL.md` — update script paths
- `skills/install.sh` — no changes needed (rsync already syncs scripts)
- After SKILL.md updates, run `skills/install.sh` to propagate to `.claude/`, `.codex/`, `.gemini/`

### Rollback

Changes are limited to SKILL.md instruction files. Reverting is a single `git revert` of the merge commit. No runtime code, database, or infrastructure changes.
