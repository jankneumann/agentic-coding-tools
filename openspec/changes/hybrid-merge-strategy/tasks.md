# Tasks: Hybrid Merge Strategy

## Phase 1: Core Script Change

- [ ] 1.1 Write tests for origin-aware strategy selection in `merge_pr.py`
  **Spec scenarios**: merge-pull-requests.merge-execution (strategy selection)
  **Dependencies**: None

- [ ] 1.2 Update `merge_pr.py` to select merge strategy based on PR origin
  - Change default from hardcoded `"squash"` to origin-aware lookup
  - Strategy mapping: `openspec`/`codex` → `rebase`, all others → `squash`
  - Preserve `--strategy` CLI override (operator can always override)
  - Update `merge()` function to pass resolved strategy to `gh pr merge`
  **Dependencies**: 1.1

- [ ] 1.3 Verify existing tests still pass with new default logic
  **Dependencies**: 1.2

## Phase 2: Skill Documentation Updates

- [ ] 2.1 Update `skills/merge-pull-requests/SKILL.md`
  - Change "squash by default" to document hybrid strategy
  - Add origin-strategy mapping table
  - Update merge action description and examples
  - Note operator override capability
  **Dependencies**: 1.2

- [ ] 2.2 Update `skills/cleanup-feature/SKILL.md`
  - Update merge examples to show rebase-merge for OpenSpec PRs
  - Keep squash as alternative example
  - Add note about strategy selection rationale
  **Dependencies**: None

- [ ] 2.3 Update `skills/implement-feature/SKILL.md`
  - Add commit quality section requiring logical, conventional commits
  - One commit per task (not one giant commit, not WIP fragments)
  - Document that rebase-merge preserves these commits on main
  - Explain why commit quality matters now (history is preserved)
  **Dependencies**: None

## Phase 3: Project-Level Documentation

- [ ] 3.1 Update `CLAUDE.md` git conventions section
  - Add merge strategy policy (hybrid, origin-aware)
  - Add commit quality expectations for agent-authored PRs
  **Dependencies**: 2.1

- [ ] 3.2 Update `docs/skills-workflow.md`
  - Add merge strategy rationale section
  - Document the hybrid approach and why squash alone is insufficient for agentic workflows
  **Dependencies**: 2.1

- [ ] 3.3 Add merge strategy entry to `docs/lessons-learned.md`
  - Document the squash-merge branch detection problem
  - Document the hybrid solution and rationale
  **Dependencies**: None

## Phase 4: Repo Settings

- [ ] 4.1 Enable rebase-merge on the GitHub repo
  - Use `gh api` to enable `allow_rebase_merge` alongside existing `allow_squash_merge`
  - Verify both methods are available
  **Dependencies**: None
