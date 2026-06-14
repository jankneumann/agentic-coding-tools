// AUTO-GENERATED from contracts/openapi/v1.yaml (in-change). Builds on PR #211's
// types.ts; only the multi-repo extensions are declared here. The full
// BoardCard union + IssueCard/PRCard shapes from PR #211 are re-exported.
//
// Regenerate after openapi/v1.yaml changes; verify with `cd apps/kanban-viz && npm run typecheck`.

// --- Re-exports from PR #211 contracts (unchanged) ---
//
// IssueCard, PRCard, ProposalCard, BoardCard, ColumnId, IssueStatus, PRStatus,
// ProposalStatus, ReviewSummary, PROrigin, CacheMeta, PRListResponse,
// CoordinatorError, assertNever — all re-exported from the PR #211 in-change
// types.ts. The SPA should import from THIS file going forward; the PR #211
// file remains the source for the inherited shapes during the v1 contracts
// in-change period.

export type {
  // PR #211 types — see openspec/changes/extend-kanban-viz-prs-proposals/contracts/generated/types.ts
  IssueStatus,
  ColumnId,
  PROrigin,
  PRStatus,
  ReviewState,
  ReviewSummary,
  PRCard,
  ProposalStatus,
  CacheMeta,
  PRListResponse,
  CoordinatorError,
} from "../../../extend-kanban-viz-prs-proposals/contracts/generated/types";

export { assertNever } from "../../../extend-kanban-viz-prs-proposals/contracts/generated/types";

// --- Multi-repo extensions to existing card kinds ---

import type {
  IssueCard as IssueCardBase,
  PRCard as PRCardBase,
  ProposalCard as ProposalCardBase,
  CacheMeta,
} from "../../../extend-kanban-viz-prs-proposals/contracts/generated/types";

/**
 * Extended IssueCard with optional client-derived repo attribution.
 * The backend `/issues/list` response shape is UNCHANGED — `repo` is computed
 * SPA-side from labels matching `^repo:<owner>/<repo>$`. Null when no such
 * label exists.
 */
export interface IssueCard extends IssueCardBase {
  readonly repo?: string | null;
}

/**
 * PRCard is unchanged — PR #211 already shipped a non-null `repo` field on
 * PR cards. Re-exported here for symmetry so consumers can import a single
 * BoardCard union from this file.
 */
export type PRCard = PRCardBase;

/**
 * Extended ProposalCard with multi-source attribution.
 *
 * `repo` is null when OPENSPEC_SOURCES is unset (PR #211 back-compat behavior:
 * single-source coordinator, no source attribution).
 *
 * `change_id_namespaced` is the canonical cluster key. Equal to
 * `<repo>/<change-id>` when repo is non-null; null otherwise.
 */
export interface ProposalCard extends ProposalCardBase {
  readonly repo: string | null;
  readonly change_id_namespaced: string | null;
}

// --- Discriminated union (rebuilt with the extended shapes) ---

export type BoardCard = IssueCard | PRCard | ProposalCard;

// --- Source-attribution metadata ---

export type SourceWarningError =
  | "local_path_missing"
  | "local_walk_failed"
  | "github_404"
  | "github_pat_denied"
  | "github_timeout"
  | "github_5xx"
  | "github_budget_exceeded";

export interface SourceWarning {
  readonly source: string;     // e.g., "github:jankneumann/foo"
  readonly error: SourceWarningError;
  readonly status?: number;
  readonly message?: string;
}

// --- Multi-source response envelope ---

export interface MultiSourceProposalListResponse {
  readonly proposals: readonly ProposalCard[];
  readonly generated_at_iso: string;
  /**
   * "live" — all contributing sources freshly fetched.
   * "cache" — all from cache.
   * "mixed" — combination (any local source is always live in this design).
   */
  readonly source: "live" | "cache" | "mixed";
  readonly cache_age_seconds: number;
  readonly _warnings?: readonly SourceWarning[];
}

// --- Saved-view shape extension ---

export interface SavedViewExtensions {
  /**
   * Optional. Cards whose `repo` matches any listed `<owner>/<repo>` entry
   * are hidden across all three rows. Pre-existing saved views (without
   * this field) continue to validate.
   */
  readonly hidden_repos?: readonly string[];
}

// --- Helpers ---

/**
 * Derive IssueCard.repo from the labels array per the label convention.
 *
 * Rules (per spec.md "Repo-Qualified IssueCard Attribution via Label Convention"):
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
 * Returns `<repo>/<change-id>` when repo is non-null.
 * Returns null when repo is null — the caller uses bare change_id as the
 * fallback key ONLY when EVERY member of the candidate cluster has repo=null
 * (see clusterBoardCards).
 */
export function getClusterKey(card: BoardCard): string | null {
  const repo = card.repo ?? null;
  if (repo == null) return null;
  const baseId =
    card.kind === "proposal"
      ? card.change_id_namespaced ?? (card.change_id ? `${repo}/${card.change_id}` : null)
      : card.change_id
        ? `${repo}/${card.change_id}`
        : null;
  return baseId;
}
