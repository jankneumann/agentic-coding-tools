# Tasks — Replace Beads with Built-in Coordinator Issue Tracker

## Phase 1: Schema & Core Service

- [ ] 1.1 Write migration `017_issue_tracking.sql` — add columns to `work_queue` and create `issue_comments` table
  **Spec scenarios**: Schema Migration (backward compatibility), Status Mapping
  **Dependencies**: None

- [ ] 1.2 Write tests for IssueService — CRUD, filtering, comments, ready/blocked queries
  **Spec scenarios**: Issue Creation (basic, epic, deps), Issue Listing (labels, parent, status), Issue Detail View, Issue Update, Issue Closure (single, batch), Issue Comments, Ready Issues Query, Blocked Issues Query, Issue Search
  **Dependencies**: 1.1

- [ ] 1.3 Implement `issue_service.py` — IssueService with create, list, show, update, close, comment, ready, blocked, search methods
  **Spec scenarios**: All ADDED requirements
  **Dependencies**: 1.2

- [ ] 1.4 Write tests for backward compatibility — verify submit_work, get_work, complete_work, get_task unchanged
  **Spec scenarios**: Work Queue Backward Compatibility (submit_work ignores issue columns)
  **Dependencies**: 1.1

- [ ] 1.5 Verify backward compatibility passes with new migration applied
  **Dependencies**: 1.3, 1.4

## Phase 2: MCP Tools

- [ ] 2.1 Write tests for MCP issue tools — tool registration, parameter validation, response format
  **Spec scenarios**: All ADDED requirements via MCP interface
  **Dependencies**: 1.3

- [ ] 2.2 Implement MCP tools in `coordination_mcp.py` — issue_create, issue_list, issue_show, issue_update, issue_close, issue_comment, issue_ready, issue_blocked, issue_search
  **Dependencies**: 2.1

- [ ] 2.3 Add HTTP API endpoints for issue tools in `coordination_api.py`
  **Dependencies**: 2.2

## Phase 3: Skill Migration

- [ ] 3.1 Replace `openspec-beads-worktree` skill — use coordinator issue_create/issue_list/issue_close instead of bd commands
  **Dependencies**: 2.2

- [ ] 3.2 Update `cleanup-feature` skill Step 5 — replace `bd create` / `bd dep add` with issue_create MCP calls
  **Dependencies**: 2.2

- [ ] 3.3 Update CLAUDE.md — remove `bd sync` from session close protocol, remove beads references from hooks documentation
  **Dependencies**: 2.2

- [ ] 3.4 Remove beads git hooks — remove `bd sync --flush-only` from pre-commit, remove `bd import` from post-merge
  **Dependencies**: 3.1, 3.2

## Phase 4: Cleanup & Migration

- [ ] 4.1 Write migration script — export existing beads issues from `.beads/issues.jsonl` and import into coordinator work_queue
  **Dependencies**: 2.2

- [ ] 4.2 Remove `.beads/` directory and configuration
  **Dependencies**: 4.1, 3.4

- [ ] 4.3 Remove beads plugin skills — delete all `beads:*` skill registrations
  **Dependencies**: 4.2

- [ ] 4.4 Update `skills/install.sh` — remove any beads-related sync logic
  **Dependencies**: 4.3

- [ ] 4.5 Update documentation — remove beads references from docs/skills-workflow.md, docs/lessons-learned.md, memory files
  **Dependencies**: 4.2
