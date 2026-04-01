# Implementation Tasks

## Task 1: Update implement-feature skill

**Files**: `skills/implement-feature/SKILL.md`

Add Step 2.5 (Worktree Setup) after validation, before branch creation:

- [x] Add worktree creation logic with path `../<repo-name>.worktrees/<change-id>/`
- [x] Create feature branch if it doesn't exist
- [x] Create worktree pointing to feature branch
- [x] Skip worktree creation if already in the correct worktree
- [x] Change working directory to worktree
- [x] Update Step 3 to skip branch creation if branch already exists

**Dependencies**: None

---

## Task 2: Update cleanup-feature skill

**Files**: `skills/cleanup-feature/SKILL.md`

Add Step 7.5 (Worktree Cleanup) after archive, before final verification:

- [x] Detect if worktree exists for the change-id
- [x] Change to main repo before removing worktree
- [x] Remove worktree using `git worktree remove`

**Dependencies**: None

---

## Task 3: Update iterate-on-implementation skill

**Files**: `skills/iterate-on-implementation/SKILL.md`

Add worktree detection at start of skill:

- [x] Add worktree context detection logic
- [x] Set `$OPENSPEC_PATH` variable based on worktree detection
- [x] Update all OpenSpec file references to use `$OPENSPEC_PATH`

**Dependencies**: None

---

## Task 4: Update skill-workflow spec

**Files**: `openspec/specs/skill-workflow/spec.md`

Add new requirements:

- [x] Add "Worktree Isolation Pattern" requirement
- [x] Add scenario for worktree creation on implement-feature
- [x] Add scenario for worktree detection in iterate-on-implementation
- [x] Add scenario for worktree cleanup in cleanup-feature

**Dependencies**: Tasks 1, 2, 3 (spec documents implementation)
