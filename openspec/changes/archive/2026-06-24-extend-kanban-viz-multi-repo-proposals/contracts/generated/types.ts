// AUTO-GENERATED from contracts/openapi/v1.yaml (in-change).
//
// This file is a STANDALONE contract — no cross-change imports. The types
// inherited from PR #211 (now merged to main) are vendored below verbatim,
// then extended with the multi-repo additions (IssueCard.repo,
// ProposalCard.repo + change_id_namespaced, SourceWarning, etc).
//
// Why vendored, not re-exported (R1-002 fix):
//   - The SPA tsconfig has `"include": ["src"]` so it cannot import from
//     `openspec/changes/...` at all. The runtime copy lives at
//     `apps/kanban-viz/src/lib/coordinator-types.ts` (hand-synced).
//   - A relative-path re-export into the sibling PR #211 change directory
//     would break the moment that change is archived (the archive step
//     moves it to `openspec/changes/archive/<date>-.../`).
//
// Regenerate after openapi/v1.yaml changes; verify with `cd apps/kanban-viz && npm run typecheck`.

// --- Vendored from PR #211 (unchanged) ---

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

export interface ReviewSummary {
  readonly state: ReviewState;
  readonly reviewer_count: number;
  readonly last_reviewed_at_iso: string | null;
}

export type ProposalStatus = "drafted" | "in-impl";

export interface CacheMeta {
  readonly generated_at_iso: string;
  readonly source: "live" | "cache";
  readonly cache_age_seconds: number;
}

export interface CoordinatorError {
  readonly error: string;
  readonly message: string;
}

export function assertNever(x: never): never {
  throw new Error(
    `Exhaustiveness violation: unexpected discriminant ${JSON.stringify(x)}`,
  );
}

// --- IssueCard with multi-repo extension (R1-002 + Q3b) ---

/**
 * Vendored from PR #211 IssueCard + the multi-repo `repo` field.
 *
 * `repo` is OPTIONAL and CLIENT-DERIVED: the SPA computes it from labels
 * matching `^repo:<owner>/<repo>$`. The backend `/issues/list` response
 * shape is unchanged.
 *
 * `vendor`, `agent_id`, `created_at_iso`, `updated_at_iso` are OPTIONAL —
 * backend doesn't emit them; SPA derives client-side.
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

// --- PRCard (vendored from PR #211, no multi-repo extension needed) ---
//
// PRCard already carries `repo: string` (always non-null) from PR #211's
// GITHUB_REPOS fan-out. No changes for the multi-repo extension.

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

// --- ProposalCard with multi-repo extension ---

/**
 * Vendored from PR #211 ProposalCard + the multi-repo `repo` and
 * `change_id_namespaced` fields.
 *
 * `repo` is null only when origin-URL parsing AND basename derivation
 * both fail (an unreachable case in practice — the implicit `local:.`
 * source guarantees non-null repo in single-source mode).
 *
 * `change_id_namespaced` = `<repo>/<change-id>` when repo is non-null,
 * else null. This is the canonical cluster key.
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

// --- BoardCard discriminated union ---

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
  readonly source: string;
  readonly error: SourceWarningError;
  readonly status?: number;
  readonly message?: string;
}

// --- Response envelopes ---

export interface PRListResponse extends CacheMeta {
  readonly prs: readonly PRCard[];
}

export interface MultiSourceProposalListResponse {
  readonly proposals: readonly ProposalCard[];
  readonly generated_at_iso: string;
  /**
   * "live" — all contributing sources freshly fetched.
   * "cache" — all from cache.
   * "mixed" — combination (any local source is treated as fresh-per-walk).
   */
  readonly source: "live" | "cache" | "mixed";
  readonly cache_age_seconds: number;
  readonly _warnings?: readonly SourceWarning[];
}

// --- Saved-view shape extension ---

export interface SavedViewExtensions {
  /**
   * Optional. Cards whose `repo` matches any listed `<owner>/<repo>` entry
   * are hidden across all three rows.
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
 * Returns `<repo>/<change-id>` when repo is non-null. Uses the BARE
 * change_id portion — strips any leading `<repo>/` from
 * `change_id_namespaced` to avoid double-namespacing (R1-005 fix).
 *
 * Returns null when repo is null — the caller uses bare change_id as the
 * fallback key ONLY when EVERY member of the candidate cluster has
 * repo=null (see clusterBoardCards in src/hooks/useBoardCards.ts).
 */
export function getClusterKey(card: BoardCard): string | null {
  const repo = card.repo ?? null;
  if (repo == null) return null;

  // Extract the BARE change-id. For ProposalCard, change_id is the bare
  // form (without namespace); change_id_namespaced is already <repo>/<id>.
  // For IssueCard and PRCard, change_id is bare.
  const bareId = card.change_id;
  if (bareId == null) return null;

  return `${repo}/${bareId}`;
}
