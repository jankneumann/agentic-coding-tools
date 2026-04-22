# Agent Coordinator — Issue Tracking Extension

**Change**: `replace-beads-with-builtin-tracker`

## ADDED Requirements

### Requirement: Issue Creation

The system SHALL allow creating issues via MCP tool `issue_create` with title, description, issue_type (task/epic/bug/feature), priority (1-10), labels (text array), parent_id (UUID reference to another issue), assignee, and depends_on (UUID array).

The system SHALL store issues in the existing `work_queue` table with new columns for issue-specific metadata.

The system SHALL default `issue_type` to `'task'`, `priority` to `5`, and `labels` to `'{}'` when not specified.

#### Scenario: Create a basic issue
WHEN an agent calls `issue_create(title="Fix CORS headers", description="Add CORS middleware", issue_type="bug", priority=3, labels=["api", "followup"])`
THEN a new row is inserted into `work_queue` with `task_type='issue'`, the given title as description, and the new issue-specific columns populated
AND the response includes `success=true` and the new `issue_id`

#### Scenario: Create an epic with children
WHEN an agent creates an issue with `issue_type="epic"` and then creates child issues with `parent_id` referencing the epic
THEN `issue_show` on the epic returns the epic with its children listed
AND `issue_ready(parent_id=<epic_id>)` returns only children whose dependencies are satisfied

#### Scenario: Create issue with dependencies
WHEN an agent creates an issue with `depends_on=[<id1>, <id2>]`
THEN the issue is not returned by `issue_ready()` until both dependencies have status `'completed'` or `'closed'`

### Requirement: Issue Listing and Filtering

The system SHALL provide an `issue_list` MCP tool that returns issues filtered by status, issue_type, labels, parent_id, and/or assignee.

The system SHALL return issues ordered by priority (ascending) then created_at (ascending) by default.

The system SHALL support a `limit` parameter capped at 100.

#### Scenario: Filter by labels
WHEN an agent calls `issue_list(labels=["api", "followup"])`
THEN only issues whose `labels` array contains ALL specified labels are returned

#### Scenario: Filter by parent (epic children)
WHEN an agent calls `issue_list(parent_id=<epic_id>)`
THEN only issues with that `parent_id` are returned

#### Scenario: Filter by status
WHEN an agent calls `issue_list(status="open")`
THEN only issues with status in `('pending', 'claimed', 'running')` are returned
AND issues with status `'completed'`, `'failed'`, or `'cancelled'` are excluded

### Requirement: Issue Detail View

The system SHALL provide an `issue_show` MCP tool that returns full issue details including comments and child issues.

#### Scenario: Show issue with comments
WHEN an agent calls `issue_show(issue_id=<id>)`
THEN the response includes all fields of the issue plus an array of comments ordered by `created_at` ascending
AND if the issue is an epic, includes a `children` array with id, title, status of each child

### Requirement: Issue Update

The system SHALL provide an `issue_update` MCP tool that updates one or more fields: title (mapped to description), status, priority, labels, assignee, issue_type.

The system SHALL record `updated_at` on every update (using the existing `started_at` or a new timestamp as appropriate).

#### Scenario: Update issue labels
WHEN an agent calls `issue_update(issue_id=<id>, labels=["api", "urgent"])`
THEN the issue's `labels` column is replaced with the new array
AND the response includes `success=true`

#### Scenario: Update issue status
WHEN an agent calls `issue_update(issue_id=<id>, status="in_progress")`
THEN the issue's status is set to `'running'` (mapping from user-friendly names)

### Requirement: Issue Closure

The system SHALL provide an `issue_close` MCP tool that sets status to `'completed'`, records `closed_at` and optional `close_reason`.

The system SHALL support closing multiple issues in a single call via `issue_ids` array parameter.

#### Scenario: Close with reason
WHEN an agent calls `issue_close(issue_id=<id>, reason="Implemented in PR #42")`
THEN `status` is set to `'completed'`, `completed_at` is set to `now()`, and `close_reason` is set to the given reason

#### Scenario: Batch close
WHEN an agent calls `issue_close(issue_ids=[<id1>, <id2>, <id3>])`
THEN all three issues are closed in a single database transaction

### Requirement: Issue Comments

The system SHALL provide an `issue_comment` MCP tool that appends a comment to an issue.

Comments SHALL be stored in a separate `issue_comments` table with `issue_id`, `author`, `body`, and `created_at`.

#### Scenario: Add comment
WHEN an agent calls `issue_comment(issue_id=<id>, body="Started work on this")`
THEN a new row is inserted into `issue_comments` with the agent's ID as author
AND `issue_show` includes this comment in the comments array

### Requirement: Ready Issues Query

The system SHALL provide an `issue_ready` MCP tool that returns issues with no unresolved dependencies, optionally scoped to children of a parent.

#### Scenario: Ready issues for epic
WHEN an agent calls `issue_ready(parent_id=<epic_id>)`
THEN only children of that epic whose `depends_on` dependencies are all completed/closed are returned
AND issues with status `'completed'` or `'cancelled'` are excluded from results

### Requirement: Blocked Issues Query

The system SHALL provide an `issue_blocked` MCP tool that returns issues with at least one unresolved dependency.

#### Scenario: List blocked issues
WHEN an agent calls `issue_blocked()`
THEN issues whose `depends_on` array contains at least one ID with status NOT in `('completed')` are returned

### Requirement: Issue Search

The system SHALL provide an `issue_search` MCP tool that performs text matching across issue title (description) and body (input_data.description or metadata.body).

#### Scenario: Search by keyword
WHEN an agent calls `issue_search(query="CORS")`
THEN issues whose description or metadata contain "CORS" (case-insensitive) are returned

### Requirement: Schema Migration

The system SHALL add new columns to `work_queue` via a numbered migration file following the existing pattern (`017_issue_tracking.sql`).

New columns SHALL be nullable with defaults to avoid breaking existing work_queue consumers.

The migration SHALL create the `issue_comments` table and appropriate indexes.

#### Scenario: Backward compatibility
WHEN existing code calls `submit_work(task_type="test", description="Run tests")`
THEN the task is created successfully with `labels='{}'`, `parent_id=NULL`, `issue_type='task'`, `assignee=NULL`
AND existing `get_work`, `complete_work`, and `get_task` tools continue to function unchanged

### Requirement: Status Mapping

The system SHALL map user-friendly status names to work_queue statuses:
- `"open"` → `'pending'`
- `"in_progress"` → `'running'`
- `"closed"` → `'completed'`
- `"blocked"` — computed from unresolved dependencies, not a stored status

#### Scenario: Status translation in listing
WHEN an agent calls `issue_list(status="open")`
THEN the query filters for `status IN ('pending', 'claimed')` in work_queue

### Requirement: Issue Bridge Helpers

The coordinator HTTP bridge (`skills/coordination-bridge/scripts/coordination_bridge.py`) SHALL expose a uniform set of helper functions — one per issue HTTP endpoint — so non-MCP callers (orchestrator scripts, CI jobs, shell pipelines wrapping `python3`) can invoke issue operations with the same normalized `{status, operation, response, ...}` envelope used by the existing `try_lock`, `try_handoff_write`, and other bridge helpers.

The bridge SHALL define a new capability flag `CAN_ISSUES` and register a probe at `POST /issues/list` with an empty body so `detect_coordination` can advertise issue availability alongside other capabilities.

The bridge SHALL provide the following helpers, each accepting keyword-only arguments matching the corresponding HTTP endpoint's request model and delegating to `_execute_single_endpoint_operation`:

- `try_issue_create` → `POST /issues/create`
- `try_issue_list` → `POST /issues/list`
- `try_issue_show` → `GET /issues/{issue_id}`
- `try_issue_update` → `POST /issues/update`
- `try_issue_close` → `POST /issues/close`
- `try_issue_comment` → `POST /issues/comment`
- `try_issue_ready` → `POST /issues/ready`
- `try_issue_blocked` → `GET /issues/blocked` (with `limit` as query parameter)
- `try_issue_search` → `POST /issues/search`

Optional helper arguments that receive `None` SHALL be omitted from the outgoing payload so server-side defaults apply cleanly.

#### Scenario: Capability probe advertises CAN_ISSUES
WHEN `detect_coordination()` is called against a coordinator where `POST /issues/list` returns `200` with `{"success": true, "issues": [], "count": 0}`
THEN the returned state dict contains `CAN_ISSUES: true`

#### Scenario: Helper skips when capability is unavailable
WHEN `try_issue_create(title="x")` is called and `detect_coordination()` reports `CAN_ISSUES: false`
THEN the helper returns `{"status": "skipped", "reason": "capability_unavailable", ...}` without issuing an HTTP request

#### Scenario: Helper degrades on unreachable coordinator
WHEN `try_issue_create(title="x")` is called, `CAN_ISSUES` is `true`, but the HTTP request times out (status_code is `None`)
THEN the helper returns `{"status": "skipped", "reason": "coordinator_unreachable", ...}`

#### Scenario: Batch close uses issue_ids field
WHEN `try_issue_close(issue_ids=["a", "b"])` is called
THEN the outgoing payload equals `{"issue_ids": ["a", "b"]}` — no stray `"issue_id": null` key

#### Scenario: Blocked helper encodes limit as query parameter
WHEN `try_issue_blocked(limit=7)` is called
THEN the HTTP request uses method `GET` and path `/issues/blocked?limit=7` with no request body

### Requirement: Work Queue Issue Extension Backward Compatibility

Adding issue-tracking columns to `work_queue` SHALL preserve the existing behavior of `submit_work`, `get_work`, `complete_work`, and `get_task` MCP tools without modification.

New issue-tracking columns SHALL NOT affect the behavior of existing work queue operations.

#### Scenario: submit_work ignores issue columns
WHEN `submit_work` is called without issue-specific fields
THEN the task is created with default values for all new columns
AND `get_work` returns the task without issue-specific fields in the response
