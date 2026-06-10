/**
 * TypeScript types for the Kanban board card model.
 *
 * This file re-exports the polymorphic card types (IssueCard, PRCard,
 * ProposalCard, BoardCard) from the in-change contracts source of truth,
 * then adds the stateful types (ActiveWorktree, SyncPointBlocker, etc.)
 * and the three column-mapping functions.
 *
 * Source of truth for card shapes:
 * openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types.ts
 *
 * Per task 4.3: types are copied verbatim from the contracts file and kept in
 * sync manually during v1 (no canonical contracts/ directory yet).
 */

// Re-export / copy from contracts/generated/types.ts (task 4.3)
export type {
  IssueStatus,
  ColumnId,
  IssueCard,
  PROrigin,
  PRStatus,
  ReviewState,
  ReviewSummary,
  PRCard,
  ProposalStatus,
  ProposalCard,
  BoardCard,
  CacheMeta,
  PRListResponse,
  ProposalListResponse,
  CoordinatorError,
} from "../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types";

export { assertNever } from "../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types";

// Convenience re-import for the mapping functions below
import type {
  IssueStatus,
  ColumnId,
  PRStatus,
  ProposalStatus,
} from "../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types";

/**
 * Backward-compat alias: Issue = IssueCard (without the `kind` discriminator
 * for use in the existing fixtures and legacy consumers). Deprecated — use
 * IssueCard directly. Will be removed once all consumers are migrated (5.3).
 *
 * @deprecated Use IssueCard from coordinator-types instead.
 */
export type { IssueCard as Issue } from "../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types";

/** Map from IssueStatus to Kanban column (renamed from statusToColumn). */
export function issueStatusToColumn(status: IssueStatus): ColumnId {
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

/**
 * Backward-compat alias: statusToColumn is renamed to issueStatusToColumn.
 * @deprecated Use issueStatusToColumn directly.
 */
export const statusToColumn = issueStatusToColumn;

/** Map from PRStatus to Kanban column. */
export function prStatusToColumn(status: PRStatus): ColumnId {
  switch (status) {
    case "draft":
      return "backlog";
    case "open":
    case "review":
    case "changes_requested":
      return "in-flight";
    case "approved":
      return "done";
  }
}

/** Map from ProposalStatus to Kanban column. */
export function proposalStatusToColumn(status: ProposalStatus): ColumnId {
  switch (status) {
    case "drafted":
      return "backlog";
    case "in-impl":
      return "in-flight";
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

/**
 * Raw issue shape as emitted by the SSE snapshot / /issues/list endpoint.
 * The backend does not emit the `kind` discriminator — it's added client-side.
 * We allow `kind` to be optional in the incoming shape to handle both legacy
 * backend payloads (no `kind`) and test fixtures that already include it.
 */
export type RawIssueFromBackend = Omit<
  import("../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types").IssueCard,
  "kind"
> & { kind?: "issue" };

/** Normalize a raw backend issue to an IssueCard by injecting the kind discriminator. */
export function toIssueCard(
  raw: RawIssueFromBackend,
): import("../../../../openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types").IssueCard {
  return { ...raw, kind: "issue" };
}

/** SSE snapshot event payload. */
export interface SnapshotPayload {
  work_queue: RawIssueFromBackend[];
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
