# Replace Beads with Built-in Coordinator Issue Tracker

**Change ID**: `replace-beads-with-builtin-tracker`
**Status**: Draft
**Created**: 2026-04-06

## Why

Beads (`bd` CLI) provides git-native issue tracking but feels disconnected from the rest of the system:

1. **External dependency**: Requires installing a separate Go binary (`brew tap steveyegge/beads`) on every machine and in every CI environment
2. **Redundant data model**: The coordinator's `work_queue` already tracks tasks with dependencies, priorities, statuses, and claiming — overlapping ~70% with beads functionality
3. **Integration friction**: Two git hooks (pre-commit, post-merge), a daemon process, SQLite + JSONL dual storage, and a sync branch add operational complexity
4. **Low utilization**: Only 4 issues tracked in this repo; the system's cost exceeds its value
5. **Multi-repo opportunity**: All repos using the coordinator would automatically gain issue tracking without installing beads separately

The coordinator is always running when meaningful work happens (skills check for it at startup). OpenSpec `tasks.md` covers the offline task tracking gap. There's no compelling need for an offline-first issue tracker when the coordination layer is server-dependent anyway.

## What Changes

Extend the coordinator's `work_queue` with issue-tracking features (labels, epics, comments, hierarchy) and expose them as MCP tools. Replace all beads integrations — skills, hooks, CLAUDE.md references — with coordinator-native equivalents. Remove the `.beads/` directory and `bd` dependency.

### Scope

**In scope:**
- Extend `work_queue` schema with labels, parent/child hierarchy, comments, and issue metadata
- New MCP tools for issue management (`issue_create`, `issue_list`, `issue_close`, etc.)
- Replace `openspec-beads-worktree` skill to use coordinator APIs
- Replace `cleanup-feature` beads integration (task migration step)
- Remove beads git hooks (pre-commit `bd sync`, post-merge `bd import`)
- Remove all `beads:*` plugin skills
- Update CLAUDE.md session close protocol
- Migrate existing beads issues to work_queue entries

**Out of scope:**
- Offline/disconnected operation (OpenSpec tasks.md covers this)
- Web UI for issue browsing (can query Postgres directly)
- External issue tracker sync (Jira, Linear, GitHub Issues)
- Changes to the coordinator's task claiming/execution semantics

## Approaches Considered

### Approach A: In-Table Extension (Recommended)

Add issue-specific columns directly to the `work_queue` table and new MCP tools.

**Schema additions:**
```sql
ALTER TABLE work_queue ADD COLUMN labels TEXT[] DEFAULT '{}';
ALTER TABLE work_queue ADD COLUMN parent_id UUID REFERENCES work_queue(id);
ALTER TABLE work_queue ADD COLUMN issue_type TEXT DEFAULT 'task';  -- task, epic, bug, feature
ALTER TABLE work_queue ADD COLUMN assignee TEXT;
ALTER TABLE work_queue ADD COLUMN closed_at TIMESTAMPTZ;
ALTER TABLE work_queue ADD COLUMN close_reason TEXT;
ALTER TABLE work_queue ADD COLUMN metadata JSONB DEFAULT '{}';

CREATE TABLE issue_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES work_queue(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_issue_comments_issue ON issue_comments(issue_id);
```

**New MCP tools:**
- `issue_create(title, description, type?, priority?, labels?, parent_id?, assignee?, depends_on?)`
- `issue_list(status?, type?, labels?, parent_id?, assignee?)`
- `issue_show(issue_id)`
- `issue_update(issue_id, title?, description?, status?, priority?, labels?, assignee?)`
- `issue_close(issue_id, reason?)`
- `issue_comment(issue_id, body)`
- `issue_ready(parent_id?)` — list issues with no unresolved dependencies
- `issue_search(query)` — full-text search across title + description
- `issue_blocked()` — list issues blocked by open dependencies

**Pros:**
- Simplest implementation — extends existing table and service
- Tasks and issues share the same dependency system (`depends_on`)
- Agent task claiming and issue tracking are unified — an issue can be claimed and worked on
- Fewest database migrations

**Cons:**
- `work_queue` table accumulates columns that only matter for issue-tracking use cases
- Agent-facing fields (`claimed_by`, `attempt_count`, `max_attempts`) are visible on issues
- Table name "work_queue" is misleading for human-facing issues

**Effort:** M

### Approach B: Issue Service Layer

New `IssueService` class wrapping `work_queue` operations with issue-specific logic. Minimal schema additions to `work_queue` (labels, parent_id) plus a lightweight `issue_comments` table. The service provides a clean API boundary while reusing the underlying task infrastructure.

**Architecture:**
```
MCP Tools (issue_create, issue_list, ...)
    └── IssueService (issue-specific logic, validation, defaults)
         └── WorkQueue (existing task primitives)
              └── PostgreSQL (work_queue table + issue_comments table)
```

**Pros:**
- Clean separation of concerns — issue logic doesn't pollute WorkQueue class
- WorkQueue stays focused on agent task execution
- IssueService can enforce issue-specific invariants (e.g., epics can't be claimed)
- Easier to test issue behavior independently

**Cons:**
- Additional service class to maintain
- Two code paths for similar operations (issue_create vs submit_work)
- Indirection adds complexity for what is ultimately the same table

**Effort:** M

### Approach C: Separate Issues Table

New `issues` table alongside `work_queue`. Issues are the human-facing concept; work_queue stays purely for agent coordination. Issues can optionally spawn work_queue tasks when assigned to agents.

**Pros:**
- Cleanest data model — each table serves one purpose
- No risk of agent-facing semantics leaking into issue tracking
- Can evolve independently

**Cons:**
- Most complex — new table, new service, cross-table dependency tracking
- User explicitly preferred extending work_queue
- Duplicates dependency, priority, and status concepts across two tables
- Requires a linking mechanism between issues and spawned tasks

**Effort:** L

### Selected Approach

**Approach A (In-Table Extension)** — recommended because:
1. The user explicitly chose "Extend work_queue"
2. Beads issues and coordinator tasks share the same fundamental model (title, description, status, priority, dependencies)
3. The simplicity of one table outweighs the cosmetic concern of extra columns
4. The naming issue ("work_queue" vs "issues") can be addressed with a table rename in the migration

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing work_queue consumers | Medium | High | Add columns as nullable with defaults; existing submit_work/get_work unchanged |
| Losing beads issues during migration | Low | Medium | Export beads issues before migration, verify after |
| Skills referencing `bd` commands fail | Medium | Medium | Full grep + replace; test each skill after migration |
| Other repos break when beads removed | Low | Medium | Coordinator extension is additive; beads removal is per-repo |
| Git hooks fail without `bd` | Medium | Low | Remove hooks in same commit as `.beads/` removal |
