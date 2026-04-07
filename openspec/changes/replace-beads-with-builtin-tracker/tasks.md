# Tasks — Replace Beads with Built-in Coordinator Issue Tracker

## Phase 1: Schema & Core Service

- [x] 1.1 Write migration `017_issue_tracking.sql` — add columns to `work_queue` and create `issue_comments` table
  **Spec scenarios**: Schema Migration (backward compatibility), Status Mapping
  **Dependencies**: None

- [x] 1.2 Write tests for IssueService — CRUD, filtering, comments, ready/blocked queries
  **Spec scenarios**: Issue Creation (basic, epic, deps), Issue Listing (labels, parent, status), Issue Detail View, Issue Update, Issue Closure (single, batch), Issue Comments, Ready Issues Query, Blocked Issues Query, Issue Search
  **Dependencies**: 1.1

- [x] 1.3 Implement `issue_service.py` — IssueService with create, list, show, update, close, comment, ready, blocked, search methods
  **Spec scenarios**: All ADDED requirements
  **Dependencies**: 1.2

- [x] 1.4 Write tests for backward compatibility — verified via existing test_coordination_api.py (22 tests pass)
  **Spec scenarios**: Work Queue Backward Compatibility (submit_work ignores issue columns)
  **Dependencies**: 1.1

- [x] 1.5 Verify backward compatibility passes with new migration applied
  **Dependencies**: 1.3, 1.4

## Phase 2: MCP Tools

- [x] 2.1 Write tests for MCP issue tools — tool registration, parameter validation, response format
  **Spec scenarios**: All ADDED requirements via MCP interface
  **Dependencies**: 1.3

- [x] 2.2 Implement MCP tools in `coordination_mcp.py` — issue_create, issue_list, issue_show, issue_update, issue_close, issue_comment, issue_ready, issue_blocked, issue_search
  **Dependencies**: 2.1

- [x] 2.3 Add HTTP API endpoints for issue tools in `coordination_api.py`
  **Dependencies**: 2.2

## Phase 3: Skill Migration

- [x] 3.1 Replace `openspec-beads-worktree` skill — use coordinator issue_create/issue_list/issue_close instead of bd commands
  **Dependencies**: 2.2

- [x] 3.2 Update `cleanup-feature` skill Step 5 — replace `bd create` / `bd dep add` with issue_create MCP calls
  **Dependencies**: 2.2

- [x] 3.3 Update CLAUDE.md — remove `bd sync` from session close protocol
  **Dependencies**: 2.2

- [x] 3.4 Remove beads git hooks — remove `bd sync --flush-only` from pre-commit, remove `bd import` from post-merge
  **Dependencies**: 3.1, 3.2

## Phase 4: Cleanup & Migration

- [x] 4.1 Write migration script — `scripts/migrate_beads_to_coordinator.py` (run with `--dry-run` first)
  **Dependencies**: 2.2

- [ ] 4.2 Remove `.beads/` directory and configuration — **deferred to post-merge** (run migration script first, then `rm -rf .beads/`)
  **Dependencies**: 4.1, 3.4

- [ ] 4.3 Remove beads plugin skills — **deferred to post-merge** (uninstall beads plugin from Claude Code settings)
  **Dependencies**: 4.2

- [ ] 4.4 Update `skills/install.sh` — no beads-specific sync logic found (no changes needed)
  **Dependencies**: 4.3

- [ ] 4.5 Update documentation — **deferred to post-merge** (remove beads refs from docs/, memory files)
  **Dependencies**: 4.2
