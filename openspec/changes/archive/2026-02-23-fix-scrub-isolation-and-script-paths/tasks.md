# Tasks: fix-scrub-isolation-and-script-paths

## 1. Script Path Resolution Convention

- [x] 1.1 Replace repo-root-relative paths with `<agent-skills-dir>` placeholder in fix-scrub SKILL.md
  **Dependencies**: None
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Skill Script Path Resolution Convention
  **Details**: Replace all `python3 skills/fix-scrub/scripts/main.py` with `python3 <agent-skills-dir>/fix-scrub/scripts/main.py`. Add a "Script Location" note explaining the `<agent-skills-dir>` convention: agents substitute with their config directory (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`). If scripts are missing, suggest running `skills/install.sh`.

- [x] 1.2 Replace repo-root-relative paths with `<agent-skills-dir>` placeholder in bug-scrub SKILL.md
  **Dependencies**: None
  **Files**: `skills/bug-scrub/SKILL.md`
  **Traces**: Skill Script Path Resolution Convention
  **Details**: Same pattern as 1.1 — replace `python3 skills/bug-scrub/scripts/main.py` with `python3 <agent-skills-dir>/bug-scrub/scripts/main.py`. Add "Script Location" note.

- [x] 1.3 Replace repo-root-relative paths with `<agent-skills-dir>` placeholder in security-review SKILL.md
  **Dependencies**: None
  **Files**: `skills/security-review/SKILL.md`
  **Traces**: Skill Script Path Resolution Convention
  **Details**: Same pattern as 1.1 — replace `python skills/security-review/scripts/*.py` with `python3 <agent-skills-dir>/security-review/scripts/*.py`. Add "Script Location" note.

- [x] 1.4 Replace repo-root-relative paths with `<agent-skills-dir>` placeholder in merge-pull-requests SKILL.md
  **Dependencies**: None
  **Files**: `skills/merge-pull-requests/SKILL.md`
  **Traces**: Skill Script Path Resolution Convention
  **Details**: Same pattern as 1.1 — replace `python skills/merge-pull-requests/scripts/*.py` with `python3 <agent-skills-dir>/merge-pull-requests/scripts/*.py`. Add "Script Location" note.

## 2. Fix-Scrub Branch Isolation

- [x] 2.1 Add branch setup step to fix-scrub SKILL.md
  **Dependencies**: 1.1
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Fix Scrub Branch Isolation
  **Details**: Insert a new "Step 0: Branch Setup" before the current Step 1. The step SHALL: (a) pull latest main, (b) create `fix-scrub/<YYYY-MM-DD>` branch from main (with numeric suffix on collision), (c) switch to the branch. Skip branch creation if `--dry-run` is active.

- [x] 2.2 Add optional worktree setup to fix-scrub SKILL.md
  **Dependencies**: 2.1
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Fix Scrub Optional Worktree Isolation
  **Details**: Extend Step 0 with worktree logic: (a) detect if `--worktree` flag is passed or if currently in a worktree, (b) if yes, create worktree at `../<repo-name>.worktrees/fix-scrub/<date>/` using the implement-feature pattern, (c) cd into worktree. Include idempotency check (skip if already in fix-scrub worktree).

- [x] 2.3 Add PR creation step to fix-scrub SKILL.md
  **Dependencies**: 2.1
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Fix Scrub Branch Isolation (PR creation scenario)
  **Details**: Add a new "Step 6: Push and Create PR" after the existing commit step. The step SHALL: (a) push the fix-scrub branch to origin, (b) create a PR with `gh pr create` using the fix-scrub-report as the body, (c) present the PR URL. Skip if no fixes were applied.

- [x] 2.4 Update fix-scrub argument documentation
  **Dependencies**: 2.2
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Fix Scrub Optional Worktree Isolation
  **Details**: Add `--worktree` flag to the Arguments section. Document the auto-detection behavior when running inside an existing worktree.

## 3. Propagation and Validation

- [x] 3.1 Run install.sh to propagate SKILL.md changes to agent directories
  **Dependencies**: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4
  **Files**: `.claude/skills/*/SKILL.md`, `.codex/skills/*/SKILL.md`, `.gemini/skills/*/SKILL.md`
  **Traces**: All requirements (propagation)
  **Details**: Run `skills/install.sh` to rsync updated SKILL.md files to all three agent config directories. Verify the SCRIPT_DIR pattern and branch isolation steps appear in all synced copies.

- [x] 3.2 Validate OpenSpec specs
  **Dependencies**: 3.1
  **Files**: `openspec/changes/fix-scrub-isolation-and-script-paths/specs/skill-workflow/spec.md`
  **Traces**: All requirements (validation)
  **Details**: Run `openspec validate fix-scrub-isolation-and-script-paths --strict` and fix any validation errors.
