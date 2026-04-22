# Design — Replace Beads with Built-in Coordinator Issue Tracker

## Architecture

```
Skills / Hooks / CLAUDE.md
    │
    │ MCP calls (issue_create, issue_list, ...)
    ▼
┌─────────────────────────────┐
│ coordination_mcp.py         │  ← New @mcp.tool() functions
│ coordination_api.py         │  ← New HTTP endpoints
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ issue_service.py (NEW)      │  ← Issue-specific logic, validation
│                             │     wraps WorkQueueService for DB ops
│  - create()                 │
│  - list()                   │
│  - show() (+ comments)      │
│  - update()                 │
│  - close() / batch_close()  │
│  - comment()                │
│  - ready()                  │
│  - blocked()                │
│  - search()                 │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ work_queue.py (EXISTING)    │  ← Unchanged, backward compatible
│ db.py / db_postgres.py      │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ PostgreSQL (work_queue +    │  ← ALTER TABLE + new issue_comments
│ issue_comments tables)      │
└─────────────────────────────┘
```

## D1: IssueService as a Separate Class (Not Extending WorkQueueService)

**Decision**: Create `issue_service.py` with its own `IssueService` class that delegates to `DatabaseClient` directly, rather than wrapping `WorkQueueService`.

**Rationale**: WorkQueueService methods (submit, claim, complete) carry agent-coordination semantics (policy checks, guardrails, telemetry) that don't apply to issue management. Issues are human-facing tracking objects, not agent work items. Direct DB access keeps the issue service lean.

**Alternative rejected**: Extending WorkQueueService — would inherit policy checks and guardrail scanning that are inappropriate for issue CRUD.

## D2: Status Mapping Layer

**Decision**: Map user-friendly status names (`open`, `in_progress`, `closed`) to work_queue statuses (`pending`, `running`, `completed`) at the service layer, not in SQL.

**Rationale**: Skills and agents think in issue terms ("open", "closed"). The work_queue uses execution-oriented statuses ("pending", "claimed", "running"). The mapping belongs in `IssueService` where it's testable and explicit.

```python
STATUS_MAP = {
    "open": ["pending", "claimed"],
    "in_progress": ["running"],
    "closed": ["completed"],
    "all": ["pending", "claimed", "running", "completed", "failed", "cancelled"],
}
```

## D3: Labels as PostgreSQL Array (Not JSONB, Not Separate Table)

**Decision**: Store labels as `TEXT[]` column on `work_queue`.

**Rationale**: Labels are flat strings used for filtering. `TEXT[]` supports `@>` (contains) operator for efficient array overlap queries with GIN indexing. A separate labels table would be over-engineering for this use case. JSONB adds unnecessary serialization overhead.

```sql
ALTER TABLE work_queue ADD COLUMN labels TEXT[] DEFAULT '{}';
CREATE INDEX idx_work_queue_labels ON work_queue USING GIN (labels);
```

## D4: Comments in Separate Table (Not JSONB Array)

**Decision**: Store comments in `issue_comments` table, not as a JSONB array column on `work_queue`.

**Rationale**: Comments grow unboundedly, are queried independently (e.g., "show recent comments by agent X"), and benefit from their own indexes. A JSONB array would require full-column updates on each comment addition, causing write amplification.

## D5: Issue Type Discrimination via `task_type` Column

**Decision**: Use the existing `task_type` column set to `'issue'` to distinguish issues from agent work items, combined with a new `issue_type` column for issue sub-types.

**Rationale**: `get_work` filters by `task_type` — setting issues to `task_type='issue'` means they won't be accidentally claimed by agents looking for `'test'` or `'refactor'` tasks. The `issue_type` column (`task`, `epic`, `bug`, `feature`) provides the human-facing categorization.

```sql
-- Issues use task_type='issue', existing tasks keep their types
-- issue_type provides the sub-classification
ALTER TABLE work_queue ADD COLUMN issue_type TEXT DEFAULT 'task';
```

## D6: Skill Migration Strategy

**Decision**: Replace `bd` CLI commands with MCP tool calls in skills. Skills already run in a context where MCP tools are available.

**Before** (openspec-beads-worktree):
```bash
bd create --title "Implement X" --type task --priority 2
bd dep add <child-id> <parent-id>
bd close <id>
```

**After**:
```
issue_create(title="Implement X", issue_type="task", priority=3)
issue_update(issue_id=<id>, depends_on=[<parent-id>])
issue_close(issue_id=<id>)
```

Skills that reference `bd` commands in their SKILL.md instructions will be updated to reference the equivalent MCP tools. The skill logic (orchestration, worktree management) remains unchanged.

## D7: Beads Issue Migration

**Decision**: One-time Python script reads `.beads/issues.jsonl`, maps fields to work_queue columns, and inserts via coordinator API.

**Field mapping**:
| Beads Field | work_queue Column |
|---|---|
| `title` | `description` |
| `description` | `input_data.body` or `metadata.body` |
| `status` | `status` (via STATUS_MAP inverse) |
| `priority` (0-4) | `priority` (mapped to 1-10 scale) |
| `issue_type` | `issue_type` |
| `labels` | `labels` |
| `owner` | `assignee` |
| `created_at` | `created_at` |
| `closed_at` | `completed_at` |
| `close_reason` | `close_reason` |

Beads priority 0-4 maps to coordinator priority 1-10: `coordinator_priority = beads_priority * 2 + 1` (0→1, 1→3, 2→5, 3→7, 4→9).
