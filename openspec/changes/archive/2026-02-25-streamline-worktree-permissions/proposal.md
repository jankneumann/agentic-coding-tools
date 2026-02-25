# Proposal: Streamline Worktree Permissions

## Change ID
`streamline-worktree-permissions`

## Problem

When `/implement-feature` creates a git worktree, the user must manually approve every Bash tool call because:

1. **Worktree location is outside the project directory.** Worktrees are created at `../<repo-name>.worktrees/<change-id>/`, which is outside Claude Code's project permission scope (`.claude/settings.local.json`). This means ALL subsequent operations in the worktree (file reads, edits, bash commands) may trigger additional permission prompts.

2. **Complex chained bash commands don't match permission patterns.** The worktree setup is a single Bash tool call with chained `&&` commands starting with `CHANGE_ID="..."`. This doesn't match existing wildcard patterns like `Bash(git worktree add:*)` because pattern matching is based on command prefix.

The result: users must click "Allow" multiple times for every `/implement-feature` invocation — once for worktree creation, then repeatedly for operations within the worktree.

## Solution

Two complementary changes:

### 1. Relocate worktrees inside the project directory (primary)

Move worktrees from `../<repo-name>.worktrees/<change-id>/` to `.git-worktrees/<change-id>/` inside the project root:

- `.git-worktrees/` is added to `.gitignore` so worktree contents aren't tracked by the main repo
- Claude Code treats the worktree as part of the project, so project-scoped permissions apply automatically
- Eliminates permission prompts for ALL operations within worktrees, not just creation

**Path convention change:**
| Before | After |
|--------|-------|
| `../<repo-name>.worktrees/<change-id>/` | `.git-worktrees/<change-id>/` |
| `../<repo-name>.worktrees/fix-scrub/<date>/` | `.git-worktrees/fix-scrub/<date>/` |

### 2. Create Python helper script for worktree lifecycle (secondary)

Create `scripts/worktree.py` that handles worktree setup and teardown via subprocess. Skills invoke it as `python3 scripts/worktree.py setup <change-id>` — which matches the pre-approved `Bash(python3:*)` permission pattern. All git operations happen inside the script via `subprocess.run()`, bypassing Claude Code's per-command permission checks entirely.

This follows the established pattern used by `bug-scrub`, `fix-scrub`, and `security-review` skills, which wrap complex tool orchestration in Python scripts.

## Skills Affected

| Skill | Change |
|-------|--------|
| `implement-feature` | Replace inline worktree bash block with `python3 scripts/worktree.py setup <change-id>` |
| `cleanup-feature` | Replace inline worktree removal bash block with `python3 scripts/worktree.py teardown <change-id>` |
| `fix-scrub` | Replace inline worktree bash block with `python3 scripts/worktree.py setup --prefix fix-scrub <branch-name>` |
| `iterate-on-implementation` | Update path detection to check `.git-worktrees/` |
| `validate-feature` | Update path detection to check `.git-worktrees/` |
| `openspec-beads-worktree` | Update worktree path convention |
| `skill-workflow` spec | Update worktree path requirements |

Multi-runtime skill copies (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`) must be updated in sync.

## Python Script Interface

```
scripts/worktree.py setup <change-id> [--branch <branch>] [--prefix <prefix>]
scripts/worktree.py teardown <change-id> [--prefix <prefix>]
scripts/worktree.py status [<change-id>]
scripts/worktree.py detect
```

- `setup`: Creates `.git-worktrees/<change-id>/` (or `.git-worktrees/<prefix>/<id>/`), creates branch if needed, prints `WORKTREE_PATH=...`
- `teardown`: Removes the worktree and optionally the branch
- `status`: Lists active worktrees
- `detect`: Detects if running in a worktree and outputs `MAIN_REPO=...`, `OPENSPEC_PATH=...`

The script requires no external dependencies (stdlib only: `subprocess`, `pathlib`, `argparse`, `sys`).

## Migration

- Existing worktrees at `../<repo-name>.worktrees/` continue to work (git doesn't care where worktrees live)
- The `teardown` command checks both old and new locations for backward compatibility
- No migration of existing worktrees is required — they'll be cleaned up naturally via `/cleanup-feature`

## Non-Goals

- Not changing worktree-per-feature vs worktree-per-task granularity
- Not adding worktree management UI or dashboard
- Not changing how OpenSpec files are accessed from worktrees (still resolved from main repo)

## Risk Assessment

- **Low risk**: Path convention change is internal to skills, not visible to git or external tools
- **Git compatibility**: `git worktree add` works with paths inside the repo; `.gitignore` prevents tracking
- **Backward compatible**: Old worktrees still function; cleanup handles both locations
