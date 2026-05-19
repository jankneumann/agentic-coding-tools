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
  /**
   * ISO-8601 string, populated from work_queue.completed_at. Used by the Done
   * column 24-hour filter (IMPL_REVIEW R2-id=15) — proposal §3 specifies
   * `completed_at >= now() - 24h`, not the previous `updated_at` fallback.
   */
  completed_at: string | null;
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
  /** Null for single-agent worktrees keyed on change_id alone. */
  agent_id: string | null;
  /** Registry key separate from agent_id (IMPL_REVIEW F5 / gemini#3). */
  change_id: string | null;
  branch: string;
  worktree_path: string;
  last_heartbeat_iso: string;
  pinned: boolean;
  owner_session: string | null;
}

/** A single blocker row inside a SyncPointStatus.
 *
 * IMPL_REVIEW F5 / gemini#6: agent_id and change_id are surfaced SEPARATELY
 * (no fallback chaining). The kick action requires change_id to match the
 * registry; agent_id distinguishes parallel-agent worktrees from
 * single-agent worktrees (where agent_id=null and skip_agent_id must be
 * set on the kick request).
 */
export interface SyncPointBlocker {
  agent_id: string | null;
  change_id: string | null;
  last_heartbeat_iso: string;
}

/** Sync-point status row from GET /sync-points/status. */
export interface SyncPointStatus {
  skill: string;
  blocked: boolean;
  blockers: SyncPointBlocker[];
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
