/**
 * TypeScript types derived from coordinator Pydantic models.
 *
 * Generated from: agent-coordinator/src/issue_service.py (Issue dataclass)
 * and contracts/README.md.
 *
 * Design D3: no JSON sidecar — types live inline, updated manually on contract bump.
 */

/** Work queue item statuses as defined in the coordinator contract. */
export type IssueStatus =
  | "pending"
  | "claimed"
  | "running"
  | "completed"
  | "failed"
  | "blocked";

/** Minimum required fields for a Kanban card (from Issue.to_dict()). */
export interface Issue {
  id: string;
  title: string;
  body: string | null;
  status: IssueStatus;
  priority: number;
  labels: string[];
  assignee: string | null;
  /** Populated from work_queue.claimed_by (added in add-coordinator-kanban-viz). */
  claimed_by: string | null;
  /** ISO-8601 string, populated from work_queue.claimed_at. */
  claimed_at: string | null;
  created_at: string;
  updated_at: string | null;
  change_id: string | null;
  task_key: string | null;
}

/** Columns (buckets) for the Kanban board. */
export type ColumnId = "backlog" | "in-flight" | "done";

/** Map from IssueStatus to Kanban column. */
export function statusToColumn(status: IssueStatus): ColumnId {
  switch (status) {
    case "pending":
    case "blocked":
      return "backlog";
    case "claimed":
    case "running":
      return "in-flight";
    case "completed":
    case "failed":
      return "done";
  }
}

/** Active worktree entry shape from GET /worktrees/active. */
export interface ActiveWorktree {
  agent_id: string;
  branch: string;
  worktree_path: string;
  last_heartbeat_iso: string;
  pinned: boolean;
  owner_session: string | null;
}

/** Sync-point status row from GET /sync-points/status. */
export interface SyncPointStatus {
  skill: string;
  blocked: boolean;
  blockers: Array<{ agent_id: string; last_heartbeat_iso: string }>;
  suggested_actions: string[];
}

/** SSE snapshot event payload. */
export interface SnapshotPayload {
  work_queue: Issue[];
  active_agents: ActiveWorktree[];
  subscribed_change_ids: string[];
}

/** SSE transition event payload. */
export interface TransitionPayload {
  work_queue_id: string;
  from: string;
  to: string;
  agent_id: string | null;
  ts: string;
}

/** SSE audit event payload. */
export interface AuditPayload {
  audit_id: string;
  agent_id: string | null;
  operation: string;
  args_summary: string | null;
  ts: string;
}
