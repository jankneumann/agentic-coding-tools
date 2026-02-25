# Tasks: Streamline Worktree Permissions

## Task 1: Create Python worktree helper script [x]
**File**: `scripts/worktree.py`

Create `scripts/worktree.py` with four subcommands:

- `setup <change-id> [--branch <name>] [--prefix <prefix>]`:
  - Resolve main repo path (handle being called from inside a worktree)
  - Compute worktree path: `<main-repo>/.git-worktrees/<change-id>/` (or `<main-repo>/.git-worktrees/<prefix>/<id>/`)
  - If already in the target worktree, print path and exit
  - `mkdir -p` the parent directory
  - Create branch `openspec/<change-id>` (or custom `--branch`) from main if it doesn't exist
  - Run `git worktree add <path> <branch>` if worktree doesn't exist
  - Print `WORKTREE_PATH=<path>` to stdout

- `teardown <change-id> [--prefix <prefix>]`:
  - Check both `.git-worktrees/` (new) and `../<repo>.worktrees/` (legacy) locations
  - `cd` to main repo before running `git worktree remove`
  - Print confirmation

- `status [<change-id>]`:
  - List active worktrees (via `git worktree list`)
  - If change-id given, check if that specific worktree exists and print its path

- `detect`:
  - Use `git rev-parse --git-common-dir` to detect worktree context
  - Print `MAIN_REPO=<path>`, `OPENSPEC_PATH=<path>`, `IN_WORKTREE=true|false`

Requirements:
- stdlib only (subprocess, pathlib, argparse, sys, os)
- Exit code 0 on success, 1 on failure
- Machine-parseable output (KEY=VALUE lines)
- Add to `scripts/` venv or make standalone (no venv needed)

**Depends on**: nothing
**Parallel zone**: independent

---

## Task 2: Add `.git-worktrees/` to `.gitignore` [x]
**File**: `.gitignore`

Append `.git-worktrees/` to the `.gitignore` file, near the existing `.claude/settings.local.json` entry.

**Depends on**: nothing
**Parallel zone**: independent

---

## Task 3: Update implement-feature skill (all runtimes) [x]
**Files**: `skills/implement-feature/SKILL.md`, `.claude/skills/implement-feature/SKILL.md`, `.codex/skills/implement-feature/SKILL.md`, `.gemini/skills/implement-feature/SKILL.md`

Replace the inline worktree bash block (Step 2) with:

```bash
# Setup worktree for feature isolation
eval "$(python3 scripts/worktree.py setup "${CHANGE_ID}")"
cd "$WORKTREE_PATH"
echo "Working directory: $(pwd)"
```

Update the explanatory text to reference `.git-worktrees/` instead of the sibling directory.

**Depends on**: Task 1
**Parallel zone**: skills/implement-feature

---

## Task 4: Update cleanup-feature skill (all runtimes) [x]
**Files**: `skills/cleanup-feature/SKILL.md`, `.claude/skills/cleanup-feature/SKILL.md`, `.codex/skills/cleanup-feature/SKILL.md`, `.gemini/skills/cleanup-feature/SKILL.md`

Replace the inline worktree removal bash block (Step 8.5) with:

```bash
# Remove worktree
python3 scripts/worktree.py teardown "${CHANGE_ID}"
```

**Depends on**: Task 1
**Parallel zone**: skills/cleanup-feature

---

## Task 5: Update fix-scrub skill (all runtimes) [x]
**Files**: `skills/fix-scrub/SKILL.md`, `.claude/skills/fix-scrub/SKILL.md`, `.codex/skills/fix-scrub/SKILL.md`, `.gemini/skills/fix-scrub/SKILL.md`

Replace the inline worktree bash block with:

```bash
eval "$(python3 scripts/worktree.py setup "${BRANCH_DATE}" --branch "${BRANCH_NAME}" --prefix fix-scrub)"
cd "$WORKTREE_PATH"
```

**Depends on**: Task 1
**Parallel zone**: skills/fix-scrub

---

## Task 6: Update iterate-on-implementation and validate-feature skills (all runtimes) [x]
**Files**: `skills/iterate-on-implementation/SKILL.md`, `skills/validate-feature/SKILL.md`, and their `.claude/`, `.codex/`, `.gemini/` copies

Replace the inline worktree detection bash block with:

```bash
eval "$(python3 scripts/worktree.py detect)"
# IN_WORKTREE, MAIN_REPO, OPENSPEC_PATH are now set
```

Update path references from `../<repo>.worktrees/` to `.git-worktrees/`.

**Depends on**: Task 1
**Parallel zone**: skills/iterate-on-implementation, skills/validate-feature

---

## Task 7: Update openspec-beads-worktree skill (all runtimes) [x]
**Files**: `skills/openspec-beads-worktree/SKILL.md`, and its `.claude/`, `.codex/`, `.gemini/` copies

Update the `create_task_worktree()` function to use `.git-worktrees/` path convention instead of `../worktrees/`. Integrate the Python script where feasible, or update the path pattern to be consistent.

**Depends on**: Task 1
**Parallel zone**: skills/openspec-beads-worktree

---

## Task 8: Update skill-workflow spec [x]
**File**: `openspec/changes/streamline-worktree-permissions/specs/skill-workflow/spec.md`

Create a delta spec updating the worktree isolation requirements:
- Change path convention from `../<repo-name>.worktrees/` to `.git-worktrees/`
- Add requirement that worktree lifecycle is managed via `scripts/worktree.py`
- Add backward-compatibility requirement for teardown (check both locations)
- Update all scenario descriptions to reference new paths

**Depends on**: nothing
**Parallel zone**: openspec/specs

---

## Task 9: Write tests for worktree.py [x]
**File**: `scripts/tests/test_worktree.py`

Test the Python script:
- `setup` creates correct directory structure and branch
- `setup` is idempotent (re-running doesn't fail)
- `teardown` removes worktree from both new and legacy locations
- `detect` correctly identifies main repo vs worktree context
- `status` lists active worktrees
- Error cases: invalid change-id, missing git repo, etc.

Use pytest with tmp_path fixture and `git init` for test repos.

**Depends on**: Task 1
**Parallel zone**: scripts/tests
