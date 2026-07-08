// AUTO-GENERATED from contracts/openapi/v1.yaml. Do not hand-edit.
// Source of truth for SPA-side card type shapes.
//
// If the OpenAPI spec changes, regenerate this file via the contracts pipeline
// (or hand-update during early-stage development), then run `npm run typecheck`
// inside apps/kanban-viz/ to catch downstream drift.

// --- Existing Issue card (migrated from coordinator-types.ts) ---

export type IssueStatus =
  | "pending"
  | "claimed"
  | "running"
  | "completed"
  | "failed"
  | "blocked";

export type ColumnId = "backlog" | "in-flight" | "done";

/**
 * IssueCard is a superset of the existing `Issue` interface in
 * `apps/kanban-viz/src/lib/coordinator-types.ts` plus the `kind: "issue"`
 * discriminator. Every field of the previous `Issue` is preserved so the
 * SPA-side rename is mechanical (no behavior change in Card.tsx).
 *
 * Fields added by this change: `kind`, `vendor` (derived from agent_id
 * suffix; null when no vendor info). Fields preserved: `body`, `priority`,
 * `assignee`, `claimed_by`, `claimed_at`, `completed_at`, `task_key`,
 * `labels` — all consumed by the existing rendering surface.
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
  /** Derived from agent_id suffix after `--`; null when no vendor info.
   *  OPTIONAL — projected client-side in this change; the /issues/list
   *  backend does not emit `vendor` today. SPA must compute it from
   *  agent_id where available. */
  readonly vendor?: string | null;
  /** Convenience aliases (ISO 8601). OPTIONAL — projected client-side.
   *  Identical content to created_at / updated_at; SPA may use either.
   *  Backend changes to emit these natively are out of scope. */
  readonly created_at_iso?: string;
  readonly updated_at_iso?: string | null;
  /** Canonical agent identifier when claimed (mirrors claimed_by).
   *  OPTIONAL — present iff claimed_by is set. SPA-derived. */
  readonly agent_id?: string | null;
}

// --- New PR card ---

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

export interface ReviewSummary {
  readonly state: ReviewState;
  readonly reviewer_count: number;
  readonly last_reviewed_at_iso: string | null;
}

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

// --- New Proposal card ---

export type ProposalStatus = "drafted" | "in-impl";

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
}

// --- Discriminated union ---

export type BoardCard = IssueCard | PRCard | ProposalCard;

// --- Response envelopes ---

export interface CacheMeta {
  readonly generated_at_iso: string;
  readonly source: "live" | "cache";
  readonly cache_age_seconds: number;
}

export interface PRListResponse extends CacheMeta {
  readonly prs: readonly PRCard[];
}

export interface ProposalListResponse extends CacheMeta {
  readonly proposals: readonly ProposalCard[];
}

export interface CoordinatorError {
  readonly error: string;
  readonly message: string;
}

// --- Exhaustive-narrowing helper ---

export function assertNever(x: never): never {
  throw new Error(
    `Exhaustiveness violation: unexpected card kind ${JSON.stringify(x)}`,
  );
}
