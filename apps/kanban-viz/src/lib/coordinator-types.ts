/**
 * TypeScript types for the Kanban board card model.
 *
 * HAND-MAINTAINED runtime copy of the spec contract.
 * Source of truth: openspec/changes/extend-kanban-viz-multi-repo-proposals/contracts/generated/types.ts
 *
 * The SPA tsconfig has `"include": ["src"]` — it cannot import from
 * `openspec/changes/...` at all. This file is kept in sync with the
 * contracts file manually as part of every contract change.
 *
 * Extended in this change (extend-kanban-viz-multi-repo-proposals):
 *   - IssueCard gains optional `repo?: string | null`
 *   - ProposalCard gains `repo: string | null` + `change_id_namespaced: string | null`
 *   - New response envelope: MultiSourceProposalListResponse
 *   - New helpers: deriveIssueRepo, getClusterKey
 *   - New types: SourceWarning, SourceWarningError
 */

// ─────────────────────────────────────────────────────────────────────────────
// Primitive enums / scalars

export type IssueStatus =
  | "pending"
  | "claimed"
  | "running"
  | "completed"
  | "failed"
  | "blocked";

export type ColumnId = "backlog" | "in-flight" | "done";

export type PROrigin =
  | "openspec"
  | "codex"
  | "jules"
  | "dependabot"
  | "renovate"
  | "manual";

export type PRStatus =
  | "draft"
  | "open"
  | "review"
  | "changes_requested"
  | "approved";

export type ReviewState =
  | "none"
  | "commented"
  | "changes_requested"
  | "approved";

export type ProposalStatus = "drafted" | "in-impl";

// ─────────────────────────────────────────────────────────────────────────────
// Card interfaces

export interface ReviewSummary {
  readonly state: ReviewState;
  readonly reviewer_count: number;
  readonly last_reviewed_at_iso: string | null;
}

/**
 * IssueCard — vendored from PR #211 with the multi-repo `repo` field added.
 *
 * `repo` is OPTIONAL and CLIENT-DERIVED: the SPA computes it from labels
 * matching `^repo:<owner>/<repo>$`. The backend `/issues/list` response
 * shape is unchanged.
 */
export interface IssueCard {
  readonly kind: "issue";
  readonly id: string;
  readonly title: string;
  readonly body: string | null;
  readonly status: IssueStatus;
  readonly priority: number;
  readonly labels: readonly string[];
  readonly assignee: string | null;
  readonly claimed_by: string | null;
  readonly claimed_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
  readonly change_id: string | null;
  readonly task_key: string | null;
  readonly vendor?: string | null;
  readonly created_at_iso?: string;
  readonly updated_at_iso?: string | null;
  readonly agent_id?: string | null;
  /** Multi-repo extension. NULL when no `repo:<owner>/<repo>` label is set. */
  readonly repo?: string | null;
}

/** @deprecated Use IssueCard directly. */
export type Issue = IssueCard;

export interface PRCard {
  readonly kind: "pr";
  readonly id: string;
  readonly change_id: string | null;
  readonly repo: string;
  readonly number: number;
  readonly title: string;
  readonly author: string;
  readonly head_branch: string;
  readonly base_branch: string;
  readonly origin: PROrigin;
  readonly status: PRStatus;
  readonly review_summary: ReviewSummary;
  readonly is_draft: boolean;
  readonly url: string;
  readonly created_at_iso: string;
  readonly updated_at_iso: string;
}

/**
 * ProposalCard — vendored from PR #211 with multi-repo fields added.
 *
 * `repo` is null only when origin-URL parsing AND basename derivation
 * both fail (an unreachable case in practice — the implicit `local:.`
 * source guarantees non-null repo in single-source mode).
 *
 * `change_id_namespaced` = `<repo>/<change-id>` when repo is non-null,
 * else null. This is the canonical cluster key ingredient.
 */
export interface ProposalCard {
  readonly kind: "proposal";
  readonly id: string;
  readonly change_id: string;
  readonly title: string;
  readonly status: ProposalStatus;
  readonly created_at_iso: string;
  readonly updated_at_iso: string;
  readonly proposal_path: string;
  readonly has_tasks_md: boolean;
  readonly has_design_md: boolean;
  readonly has_spec_delta: boolean;
  readonly has_branch: boolean;
  readonly branch_name: string | null;
  readonly code_changes_outside_proposal: number;
  readonly repo: string | null;
  readonly change_id_namespaced: string | null;
}

export type BoardCard = IssueCard | PRCard | ProposalCard;

// ─────────────────────────────────────────────────────────────────────────────
// Source-attribution metadata (new in this change)

export type SourceWarningError =
  | "local_path_missing"
  | "local_walk_failed"
  | "github_404"
  | "github_pat_denied"
  | "github_timeout"
  | "github_5xx"
  | "github_budget_exceeded";

export interface SourceWarning {
  readonly source: string;
  readonly error: SourceWarningError;
  readonly status?: number;
  readonly message?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Response envelopes

export interface CacheMeta {
  readonly generated_at_iso: string;
  readonly source: "live" | "cache";
  readonly cache_age_seconds: number;
}

export interface PRListResponse extends CacheMeta {
  readonly prs: readonly PRCard[];
}

/**
 * PR #211 single-source envelope (back-compat). Used for local-only single-
 * source mode where `source` is "live" or "cache" (no "mixed").
 */
export interface ProposalListResponse extends CacheMeta {
  readonly proposals: readonly ProposalCard[];
}

/**
 * Multi-source response envelope (this change). Wire-compatible with PR #211's
 * ProposalListResponse — adds optional `_warnings` and widens `source` enum.
 */
export interface MultiSourceProposalListResponse {
  readonly proposals: readonly ProposalCard[];
  readonly generated_at_iso: string;
  readonly source: "live" | "cache" | "mixed";
  readonly cache_age_seconds: number;
  readonly _warnings?: readonly SourceWarning[];
}

export interface CoordinatorError {
  readonly error: string;
  readonly message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Exhaustive-narrowing helper

export function assertNever(x: never): never {
  throw new Error(
    `Exhaustiveness violation: unexpected discriminant ${JSON.stringify(x)}`,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Column-mapping helpers

/** Map from IssueStatus to Kanban column. */
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

/** @deprecated Use issueStatusToColumn directly. */
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

// ─────────────────────────────────────────────────────────────────────────────
// Stateful types (SPA-internal, not in contracts)

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

export interface SyncPointBlocker {
  agent_id: string | null;
  change_id: string | null;
  last_heartbeat_iso: string;
}

export interface SyncPointStatus {
  skill: string;
  blocked: boolean;
  blockers: SyncPointBlocker[];
  suggested_actions: string[];
}

/**
 * Raw issue shape as emitted by the SSE snapshot / /issues/list endpoint.
 * The backend does not emit the `kind` discriminator — it's added client-side.
 */
export type RawIssueFromBackend = Omit<IssueCard, "kind"> & { kind?: "issue" };

/** Normalize a raw backend issue to an IssueCard by injecting the kind discriminator. */
export function toIssueCard(raw: RawIssueFromBackend): IssueCard {
  return { ...raw, kind: "issue" };
}

export interface SnapshotPayload {
  work_queue: RawIssueFromBackend[];
  active_agents: ActiveWorktree[];
  subscribed_change_ids: string[];
}

export interface TransitionPayload {
  work_queue_id: string;
  from: string;
  to: string;
  agent_id: string | null;
  ts: string;
}

export interface AuditPayload {
  audit_id: string;
  agent_id: string | null;
  operation: string;
  args_summary: string | null;
  ts: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Multi-repo helpers (new in this change)

/**
 * Derive IssueCard.repo from the labels array per the label convention.
 *
 * Rules:
 *   1. Scan labels for the FIRST entry matching `^repo:<owner>/<repo>$`.
 *   2. Strip the `repo:` prefix.
 *   3. Lowercase the remainder.
 *   4. Return that value, or null if no match.
 *
 * When multiple `repo:` labels are present, the first wins and a
 * console.warn names the conflicting labels.
 */
export function deriveIssueRepo(labels: readonly string[]): string | null {
  const pattern = /^repo:([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)$/;
  const matches = labels
    .map((l) => l.match(pattern))
    .filter((m): m is RegExpMatchArray => m !== null)
    .map((m) => m[1].toLowerCase());

  if (matches.length > 1) {
    // eslint-disable-next-line no-console
    console.warn(
      `[deriveIssueRepo] issue has multiple repo: labels; using first`,
      matches,
    );
  }

  return matches[0] ?? null;
}

/**
 * Cluster key for a BoardCard.
 *
 * Returns `<repo>/<change-id>` when repo is non-null. Uses the BARE
 * change_id portion to avoid double-namespacing (R1-005 fix).
 *
 * Returns null when repo is null — the caller uses bare change_id as the
 * fallback key ONLY when EVERY member of the candidate cluster has
 * repo=null (see clusterBoardCards in src/hooks/useBoardCards.ts).
 */
export function getClusterKey(card: BoardCard): string | null {
  const repo = card.repo ?? null;
  if (repo == null) return null;

  // Use the BARE change-id. For ProposalCard, change_id is the bare form
  // (without namespace). For IssueCard and PRCard, change_id is bare.
  const bareId = card.change_id;
  if (bareId == null) return null;

  return `${repo}/${bareId}`;
}
