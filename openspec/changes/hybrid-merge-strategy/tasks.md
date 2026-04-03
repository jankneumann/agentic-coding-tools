# Tasks: Hybrid Merge Strategy

## Phase 1: Core Script Change

- [x] 1.1 Write tests for origin-aware strategy selection in `merge_pr.py`
  **Spec scenarios**: "Agent-authored PR uses rebase-merge by default", "Dependency PR uses squash-merge by default", "Automation PR uses squash-merge by default", "Operator overrides default strategy via CLI flag", "Rebase-merge fails due to merge conflicts"
  **Dependencies**: None

- [x] 1.2 Update `merge_pr.py` to select merge strategy based on PR origin
  - Add `get_default_strategy(origin: str) -> str` function with origin-to-strategy mapping
  - `openspec`/`codex` → `rebase`, all others → `squash`
  - Change `merge_pr()` (line 354) to accept optional `origin` parameter
  - When `--strategy` is not explicitly provided and `--origin` is given, use `get_default_strategy(origin)`
  - Update CLI `--strategy` default from `"squash"` to `None` (sentinel for "use origin default")
  - Update `--strategy` help text to document origin-aware defaults
  - Preserve explicit `--strategy` override (operator can always override)
  **Dependencies**: 1.1

- [x] 1.3 Verify existing tests still pass with new default logic
  **Dependencies**: 1.2

## Phase 2: Skill Documentation Updates (2.2, 2.3 can run parallel with Phase 1)

- [x] 2.1 Update `skills/merge-pull-requests/SKILL.md`
  - Change "squash by default" to document hybrid strategy
  - Add origin-strategy mapping table
  - Update Step 11 merge action description and examples
  - Update `merge_pr.py merge <pr> --strategy squash` examples to show `--origin <origin>`
  - Note operator override capability
  **Dependencies**: 1.2

- [x] 2.2 Update `skills/cleanup-feature/SKILL.md`
  - Update merge examples to show `--rebase` for OpenSpec PRs
  - Keep squash as alternative example for non-OpenSpec PRs
  - Add note about strategy selection rationale
  **Dependencies**: None

- [x] 2.3 Update `skills/implement-feature/SKILL.md`
  - Add commit quality section requiring logical, conventional commits
  - One commit per task (not one giant commit, not WIP fragments)
  - Document that rebase-merge preserves these commits on main
  - Explain why commit quality matters now (history is preserved)
  **Dependencies**: None

## Phase 3: Project-Level Documentation (3.3 can run parallel with everything)

- [x] 3.1 Update `CLAUDE.md` git conventions section
  - Add merge strategy policy (hybrid, origin-aware)
  - Add commit quality expectations for agent-authored PRs
  **Dependencies**: 2.1

- [x] 3.2 Update `docs/skills-workflow.md`
  - Add merge strategy rationale section
  - Document the hybrid approach and why squash alone is insufficient for agentic workflows
  **Dependencies**: 2.1

- [x] 3.3 Add merge strategy entry to `docs/lessons-learned.md`
  - Document the squash-merge branch detection problem
  - Document the hybrid solution and rationale
  **Dependencies**: None

## Phase 4: Repo Settings (can run parallel with everything)

- [x] 4.1 Enable rebase-merge on the GitHub repo
  - Use `gh api -X PATCH repos/{owner}/{repo} -f allow_rebase_merge=true` to enable alongside existing squash
  - Verify both methods are available with `gh api repos/{owner}/{repo} --jq '.allow_rebase_merge, .allow_squash_merge'`
  **Dependencies**: None

## Parallelizability

- **Independent tasks**: 2.2, 2.3, 3.3, 4.1 (can all run in parallel, no shared files)
- **Sequential chains**: 1.1 → 1.2 → 1.3 → 2.1 → 3.1, 3.2
- **Max parallel width**: 4 (tasks 2.2, 2.3, 3.3, 4.1 during Phase 1 execution)
- **File overlap conflicts**: None — each task touches distinct files
