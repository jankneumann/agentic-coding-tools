# coordinator-kanban-viz Spec Delta — extend-kanban-viz-multi-repo-proposals

This delta extends the existing `coordinator-kanban-viz` spec (as enhanced by
PR #211 / extend-kanban-viz-prs-proposals) with multi-repository support
spanning all three card streams. All new requirements are ADDED. No existing
requirement is MODIFIED or REMOVED — the new fields on `ProposalCard` and
`IssueCard` are optional (nullable / typed as `?:`) and the new `cluster_key`
resolution rule preserves bare-`change_id` behavior for back-compat data.

## ADDED Requirements

### Requirement: Multi-Repository OpenSpec Sources Configuration

The coordinator SHALL read an optional `OPENSPEC_SOURCES` environment variable as a comma-separated list of source descriptors. Each entry SHALL match one of two prefixes:

- `local:<path>` — filesystem-walk source. `<path>` is an absolute or coordinator-relative path to a checkout containing an `openspec/changes/` directory.
- `github:<owner>/<repo>` — GitHub REST API source. The coordinator fetches `openspec/changes/` directory listings via the existing `GITHUB_PAT` (the same credential already used by `GET /github/prs`).

When `OPENSPEC_SOURCES` is unset or empty, the coordinator SHALL fall back to the existing single-source behavior (the coordinator's own runtime checkout). This preserves the contract shipped in PR #211 for callers that have not yet adopted multi-repo.

The entry parser SHALL validate that `<path>` resolves to an existing directory for `local:` entries, AND that `<owner>/<repo>` matches `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` for `github:` entries (the same regex applied to `GITHUB_REPOS` in PR #211). An invalid entry SHALL cause the endpoint to respond `503` with body `{"error": "openspec_sources_invalid", "message": "<offending entry>"}` and NOT serve partial results from valid entries — failing closed matches the `github_repos_invalid` posture.

The parser SHALL normalize the `<owner>/<repo>` portion to lowercase (matching GitHub's case-insensitive lookup) before storing it in the source registry; the `repo` field on response cards SHALL likewise be lowercase.

#### Scenario: OPENSPEC_SOURCES unset falls back to single-source behavior

**WHEN** the coordinator boots with `OPENSPEC_SOURCES` unset AND a client calls `GET /openspec/proposals`
**THEN** the endpoint SHALL walk the coordinator's own `openspec/changes/` directory (the PR #211 behavior)
**AND** every returned `ProposalCard` SHALL have `repo: null` (no source attribution)

#### Scenario: OPENSPEC_SOURCES mixes local and github sources

**WHEN** the coordinator boots with `OPENSPEC_SOURCES="local:/repos/agentic-coding-tools,github:jankneumann/newsletter-aggregator"` AND a client calls `GET /openspec/proposals`
**THEN** the response SHALL contain proposals from BOTH sources, merged
**AND** the `repo` field SHALL distinguish them: local source proposals SHALL carry `repo: "jankneumann/agentic-coding-tools"` (resolved via `git remote get-url origin`), github source proposals SHALL carry `repo: "jankneumann/newsletter-aggregator"`

#### Scenario: Invalid OPENSPEC_SOURCES entry fails closed

**WHEN** `OPENSPEC_SOURCES = "local:/repos/valid,github:not_a_valid_entry"` AND a client calls `GET /openspec/proposals`
**THEN** the response status SHALL be `503`
**AND** the response body SHALL include `{"error": "openspec_sources_invalid"}`
**AND** the message SHALL name the offending entry
**AND** the endpoint SHALL NOT return proposals from the valid `local:` entry — fail closed

#### Scenario: Owner/repo casing is normalized to lowercase

**WHEN** `OPENSPEC_SOURCES = "github:JanKneumann/Newsletter-Aggregator"`
**THEN** the stored source SHALL be `github:jankneumann/newsletter-aggregator`
**AND** the response `ProposalCard.repo` field SHALL equal `"jankneumann/newsletter-aggregator"`

---

### Requirement: Hybrid Cache Strategy for Multi-Source Proposals

The endpoint SHALL apply a HYBRID cache strategy across local and github sources:

- **Local sources** SHALL be walked EAGERLY at coordinator boot and re-walked on `?refresh=true`. The walk result is cached in-process until the next boot or refresh; no TTL applies (filesystem walks are sub-millisecond per source and deterministic).
- **GitHub sources** SHALL be cached LAZILY per source with a 60-second TTL — the same TTL the PR #211 `GET /github/prs` endpoint uses. The first request to any github source triggers the fetch; subsequent requests within 60s return the cached result.
- **`?refresh=true`** SHALL bust BOTH the local re-walk cache (forcing a fresh filesystem walk for every local source) AND every github source's TTL slot (forcing fresh REST calls).

The cache SHALL coalesce concurrent requests to the same github source via a per-source mutex (single-flight pattern, matching `github_prs_api.py`). Local source re-walks are CPU-bound and short, so no mutex is required; concurrent walks are acceptable.

The response SHALL include `cache_age_seconds` as the MAXIMUM age across all source caches contributing to the response (worst-case freshness signal for the operator), and `source: "live" | "cache" | "mixed"` — `live` if all sources were freshly fetched, `cache` if all were from cache, `mixed` otherwise.

#### Scenario: Local sources warmed at boot

**WHEN** the coordinator boots with `OPENSPEC_SOURCES = "local:/repos/a,local:/repos/b"` AND a client immediately calls `GET /openspec/proposals`
**THEN** the response SHALL contain proposals from both local sources
**AND** no filesystem walk SHALL be triggered by the request — the boot warmup served the data
**AND** `cache_age_seconds` SHALL be ≈ time-since-boot (NOT > 60)

#### Scenario: GitHub source cached lazily after first request

**WHEN** the coordinator boots with `OPENSPEC_SOURCES = "github:owner/repo"` AND a client calls `GET /openspec/proposals` at T=0 and again at T=30 seconds without `?refresh=true`
**THEN** at T=0, exactly one GitHub REST call SHALL be made; the response `source` SHALL equal `"live"`
**AND** at T=30, ZERO GitHub REST calls SHALL be made; the response `source` SHALL equal `"cache"` and `cache_age_seconds` SHALL be approximately `30`

#### Scenario: refresh=true busts both local and github caches

**WHEN** a client calls `GET /openspec/proposals?refresh=true` while local sources have a stale walk AND github sources have a fresh cache
**THEN** every local source SHALL be re-walked
**AND** every github source SHALL be re-fetched
**AND** the response `source` SHALL equal `"live"`

#### Scenario: Mixed source freshness produces mixed source label

**WHEN** the response is assembled from one local source (always live in this design) and one github source still within its 60s TTL
**THEN** the response `source` SHALL equal `"mixed"`
**AND** `cache_age_seconds` SHALL be the age of the github source's cache entry (the worst case)

---

### Requirement: Multi-Source ProposalCard Fields

The `ProposalCard` shape returned by `GET /openspec/proposals` SHALL be extended with the following fields:

- `repo` (string or null) — the `<owner>/<repo>` identifier of the source this proposal came from. For `github:` sources, this is the lowercase-normalized github source entry. For `local:` sources, this is derived from `git remote get-url origin` (parsed for `owner/repo`), falling back to the checkout's basename if origin parsing fails (a warning is logged on fallback). When `OPENSPEC_SOURCES` is unset, `repo` SHALL be `null` (back-compat with PR #211 behavior).
- `change_id_namespaced` (string or null) — equal to `<repo>/<change-id>` when `repo` is non-null, otherwise `null`. This is the canonical cluster key for cross-source linkage.

All other `ProposalCard` fields from PR #211 SHALL be preserved unchanged: `kind`, `id`, `change_id`, `title`, `status`, `created_at_iso`, `updated_at_iso`, `proposal_path`, `has_tasks_md`, `has_design_md`, `has_spec_delta`, `has_branch`, `branch_name`, `code_changes_outside_proposal`.

For `github:` sources, the `proposal_path` SHALL be the github web URL to the `proposal.md` file (`https://github.com/<owner>/<repo>/blob/<branch>/openspec/changes/<change-id>/proposal.md`), NOT a local filesystem path. This lets the SPA render a "View on GitHub" link uniformly. For `local:` sources, `proposal_path` remains a repo-relative path as in PR #211.

For `github:` sources, the `has_branch` + `branch_name` + `code_changes_outside_proposal` fields SHALL be derived by checking the GitHub REST `/repos/{owner}/{repo}/branches/openspec/{change-id}` endpoint (or `claude/{change-id}` if the former 404s) and counting commits via `/repos/{owner}/{repo}/compare/main...openspec/{change-id}` with a path filter. When the branch doesn't exist, `has_branch: false` AND `code_changes_outside_proposal: 0` SHALL be returned.

#### Scenario: ProposalCard from local source has lowercase repo and namespaced id

**WHEN** a local source at `/repos/agentic-coding-tools` is configured AND the repo's `git remote get-url origin` returns `https://github.com/JanKneumann/Agentic-Coding-Tools.git`
**THEN** every `ProposalCard` from that source SHALL have `repo: "jankneumann/agentic-coding-tools"` (lowercase)
**AND** for a change with `change_id: "foo"`, `change_id_namespaced` SHALL equal `"jankneumann/agentic-coding-tools/foo"`

#### Scenario: GitHub-source ProposalCard has github URL in proposal_path

**WHEN** a github source `github:jankneumann/newsletter-aggregator` is configured AND the repo has `openspec/changes/foo/proposal.md` on the default branch (`main`)
**THEN** the returned `ProposalCard.proposal_path` SHALL equal `"https://github.com/jankneumann/newsletter-aggregator/blob/main/openspec/changes/foo/proposal.md"`
**AND** the SPA SHALL render this as a clickable "View on GitHub" link (NOT as a local-path tooltip)

#### Scenario: GitHub-source branch-existence probe used for in-impl detection

**WHEN** a github source has `openspec/changes/bar/proposal.md` AND a branch named `openspec/bar` exists with 3 commits ahead of main, 2 of which touch `coordinator/foo.py`
**THEN** the returned `ProposalCard` SHALL have `has_branch: true`, `branch_name: "openspec/bar"`, `code_changes_outside_proposal: 2`, and `status: "in-impl"`

#### Scenario: Repo derivation falls back to basename with warning

**WHEN** a local source at `/repos/orphan-checkout` has NO git remote configured (or `git remote get-url origin` exits non-zero)
**THEN** the derived `repo` value SHALL be `"orphan-checkout"` (the basename of the checkout directory)
**AND** a warning-level log entry SHALL be emitted naming the source and the fallback reason
**AND** the response SHALL still return the proposals from that source — the fallback is non-fatal

---

### Requirement: Repo-Qualified IssueCard Attribution via Label Convention

The SPA SHALL derive `IssueCard.repo` client-side from the issue's `labels` array. The derivation rule:

1. Scan the labels array for the FIRST entry matching the pattern `^repo:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`.
2. Strip the `repo:` prefix.
3. Lowercase the remainder.
4. Use that value as `IssueCard.repo`.

If no matching label is found, `IssueCard.repo` SHALL equal `null`. The derivation SHALL be a pure function with no network or coordinator side effects.

The `work_queue` table SHALL NOT undergo a schema migration. The label convention reuses the existing `labels` array (already a `text[]` column). Skills and agents that want to attribute work to a specific repo write a `repo:<owner>/<repo>` label alongside their other labels using the existing `PATCH /issues/{id}/labels` endpoint.

The coordinator endpoint `GET /issues/list` response shape SHALL be UNCHANGED — the derivation happens entirely SPA-side. This preserves the contract for non-kanban-viz consumers of `/issues/list`.

The SPA SHALL display `IssueCard.repo === null` cards without a repo badge (they participate in clusters via the bare `change_id` fallback documented in the Namespaced Cluster Key requirement).

#### Scenario: Issue with repo label gets a derived repo field

**WHEN** an issue has `labels = ["repo:jankneumann/agentic-coding-tools", "priority:high"]`
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `"jankneumann/agentic-coding-tools"`
**AND** the rendered card SHALL show the RepoBadge with that value

#### Scenario: Issue with no repo label has null repo

**WHEN** an issue has `labels = ["pending-approval", "priority:medium"]` AND no `repo:` prefix entry exists
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `null`
**AND** the card SHALL NOT render a RepoBadge

#### Scenario: Issue with multiple repo labels uses the first

**WHEN** an issue has `labels = ["repo:jankneumann/a", "repo:jankneumann/b"]` (operator error or intentional cross-tagging)
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `"jankneumann/a"` (first occurrence wins)
**AND** a warning SHALL be logged to the browser console naming the issue id and the conflicting labels

#### Scenario: Label casing is normalized to lowercase

**WHEN** an issue has `labels = ["repo:JanKneumann/Agentic-Coding-Tools"]` (mixed case)
**THEN** the derived `IssueCard.repo` SHALL equal `"jankneumann/agentic-coding-tools"` (lowercase)

---

### Requirement: Namespaced Cluster Key Resolution

The SPA's cluster computation function `clusterBoardCards` SHALL key clusters by `change_id_namespaced` (the form `<repo>/<change-id>`) for the standard path, AND SHALL fall back to bare `change_id` ONLY when EVERY card in a candidate cluster has `repo: null` (back-compat with pre-multi-repo data — i.e., a single-source coordinator where `OPENSPEC_SOURCES` is unset).

This means:

- Cards with non-null repos cluster only when their `<repo>/<change-id>` matches exactly. Two cards with `change_id: "fix-auth"` in DIFFERENT repos do NOT cluster (this is the safety guarantee).
- Cards with `repo: null` cluster by bare `change_id` — preserving PR #211's behavior for single-source coordinators.
- A cluster CANNOT mix repo-null and repo-non-null members. If a candidate cluster would mix them, the function SHALL split into separate clusters (the repo-null group, plus one cluster per distinct repo).

The fallback behavior SHALL be unit-tested against a fixture board containing both pre-multi-repo data (all `repo: null`) AND multi-repo data (all `repo` set) to confirm the back-compat path works without regressing PR #211 behavior.

A future "cross-repo cluster registry" extension (deferred — see proposal Open Questions) would add an OPTIONAL override layer that lets explicit `change_id_aliases` link cards across repos. The current requirement is structured so that registry can layer on without rewriting `clusterBoardCards`'s core key resolution.

#### Scenario: Same-repo cluster uses namespaced key

**WHEN** the board contains an `IssueCard` and a `PRCard` both with `repo: "jankneumann/agentic-coding-tools"` and `change_id: "add-langfuse-tracing"`
**THEN** they SHALL cluster together
**AND** each card's `cluster_count` SHALL equal `2`

#### Scenario: Same change_id across repos does NOT cluster

**WHEN** the board contains a `PRCard` with `repo: "jankneumann/agentic-coding-tools"` and `change_id: "fix-auth"`, AND a `PRCard` with `repo: "jankneumann/newsletter-aggregator"` and `change_id: "fix-auth"`
**THEN** they SHALL NOT cluster together
**AND** each card's `cluster_count` SHALL equal `1` (singleton — no badge rendered)

#### Scenario: All-null-repo cluster falls back to bare change_id

**WHEN** the board is populated from a single-source coordinator (`OPENSPEC_SOURCES` unset) AND contains an `IssueCard`, `PRCard`, `ProposalCard` all with `repo: null` and `change_id: "foo"`
**THEN** they SHALL cluster together via the bare `change_id` fallback
**AND** each card's `cluster_count` SHALL equal `3`

#### Scenario: Mixed null and non-null repos split into separate clusters

**WHEN** the board contains an `IssueCard` with `repo: null, change_id: "foo"` and a `PRCard` with `repo: "x/y", change_id: "foo"`
**THEN** they SHALL NOT cluster together
**AND** the IssueCard's `cluster_count` SHALL equal `1`
**AND** the PRCard's `cluster_count` SHALL equal `1`

---

### Requirement: Per-Card Repo Badge Component

The SPA SHALL render a `RepoBadge` micro-component on `IssueCardView`, `PRCardView`, and `ProposalCardView` whenever the card's `repo` field is non-null. The badge SHALL:

- Display the short form of the repo (the `<repo>` portion after the `/`) by default.
- On hover, show the full `<owner>/<repo>` as a tooltip.
- Use a deterministic per-repo color derived from a hash of the full `<owner>/<repo>` string (so the same repo always gets the same color across the board, helping operators visually group cards by repo).
- Be accessible — `aria-label` SHALL include the full `<owner>/<repo>` so screen readers don't lose the qualifier.

Cards with `repo: null` SHALL NOT render a RepoBadge. The visual treatment for repo-less cards SHALL remain identical to PR #211 (no behavioral regression for single-source boards).

The hash-to-color function SHALL be deterministic and seeded only by the repo string — no randomization, no per-session state. This makes the visual mapping stable across SPA reloads and across operators sharing the same board.

#### Scenario: RepoBadge renders short form with full tooltip

**WHEN** an `IssueCard` has `repo: "jankneumann/agentic-coding-tools"`
**THEN** the rendered DOM SHALL contain a RepoBadge with visible text `"agentic-coding-tools"`
**AND** the badge's title attribute (tooltip) SHALL equal `"jankneumann/agentic-coding-tools"`
**AND** the badge's `aria-label` SHALL equal `"Repository jankneumann/agentic-coding-tools"`

#### Scenario: Repo-null card omits badge entirely

**WHEN** a `PRCard` has `repo: null`
**THEN** the rendered card SHALL NOT contain any `RepoBadge` element
**AND** the card layout SHALL be visually identical to PR #211's PR card rendering

#### Scenario: Color stable across reloads

**WHEN** an `IssueCard` and `PRCard` both have `repo: "jankneumann/agentic-coding-tools"`
**THEN** their RepoBadges SHALL render with the IDENTICAL background color
**AND** the color SHALL be the same value on every page reload (deterministic, hash-seeded)

---

### Requirement: Hidden Repos Saved-View Field

The coordinator's saved-view JSON schema at `agent-coordinator/src/schemas/kanban_viz/saved-view.json` SHALL be extended with an optional `hidden_repos` field under `view`. The field SHALL be an array of `<owner>/<repo>` strings; cards whose `repo` matches any listed entry SHALL be hidden from the board (across all three rows).

The field SHALL be optional and additive — saved views written prior to this change (with no `hidden_repos`) SHALL continue to validate.

The SPA SHALL provide a UI affordance to toggle a repo's hidden state. A reasonable implementation: clicking a RepoBadge with a modifier key (Shift) hides that repo; a "Visible repos" header chip group exposes the full list of repos that have appeared on the current board with toggle state. The exact UI is left to implementation but the persistence path MUST be the `hidden_repos` saved-view field.

#### Scenario: Saved view with hidden_repos validates

**WHEN** the SPA writes a saved view with `view.hidden_repos = ["jankneumann/scratch-repo"]`
**THEN** the coordinator schema validator SHALL accept the document as valid
**AND** the round-trip via `PUT /kanban-viz/saved-views/{slug}` then `GET` SHALL preserve the field

#### Scenario: Pre-existing saved view continues to validate

**WHEN** a saved view written before this change (with no `hidden_repos`) is loaded
**THEN** the schema validator SHALL accept it
**AND** the SPA SHALL fall back to the default (no repos hidden)

#### Scenario: Hidden repo filters all three rows

**WHEN** the board contains 5 cards from `jankneumann/repo-a` and 3 cards from `jankneumann/repo-b` AND the active saved view has `hidden_repos: ["jankneumann/repo-b"]`
**THEN** only the 5 cards from `repo-a` SHALL be visible
**AND** the row totals SHALL exclude the hidden cards
**AND** cluster computation SHALL exclude hidden cards (no orphan badges referencing hidden siblings)

---

### Requirement: Degraded Multi-Source Mode

When `GET /openspec/proposals` fans out across multiple sources, the endpoint SHALL be resilient to individual source failures. The behavior:

- If a `local:` source path does not exist, walk fails, or has no `openspec/changes/` subdirectory: skip it, emit a `_warnings` entry, return `200 OK` with the surviving sources' proposals.
- If a `github:` source returns 404 (repo not found), 401/403 (PAT lacks access), 5xx (GitHub outage), or times out (per-source timeout 10s): skip it, emit a `_warnings` entry, return `200 OK` with the surviving sources' proposals.
- If ALL configured sources fail: return `200 OK` with `proposals: []` AND a `_warnings` array listing all failures. The SPA renders the Proposals row with an empty state + partial-result chip.

The `_warnings` array SHALL be top-level in the response (sibling to `proposals`), shaped as `Array<{source: string, error: string, status?: integer}>`. Each entry SHALL name the source string (e.g., `"github:jankneumann/repo-x"`), an error code (e.g., `"github_404"`, `"local_path_missing"`, `"github_timeout"`, `"github_403"`), and the HTTP status code where applicable.

The SPA's Proposals row SHALL render a partial-result chip (warning chrome, the same chrome `changes_requested` uses on PR cards) whenever `_warnings.length > 0`. The chip SHALL show on hover or click a list of the failed sources and their errors. This pattern mirrors the per-row error chip behavior already specified for the RefreshButton in PR #211 — same UX vocabulary, different trigger.

Sources MUST be retried independently on the NEXT request (no circuit breaker pinning a source as broken across requests). This keeps the operator's mental model simple: refresh = try everything again.

#### Scenario: One github source 404s, others succeed

**WHEN** `OPENSPEC_SOURCES = "local:/repos/a,github:jankneumann/nonexistent-repo,github:jankneumann/newsletter-aggregator"` AND `jankneumann/nonexistent-repo` returns 404
**THEN** the response status SHALL be `200`
**AND** `proposals` SHALL contain proposals from `local:/repos/a` and `github:jankneumann/newsletter-aggregator` ONLY
**AND** `_warnings` SHALL contain exactly one entry: `{source: "github:jankneumann/nonexistent-repo", error: "github_404", status: 404}`

#### Scenario: All sources fail returns empty with warnings

**WHEN** all configured sources fail (e.g., all `local:` paths missing AND all `github:` repos 404)
**THEN** the response status SHALL be `200`
**AND** `proposals` SHALL equal `[]`
**AND** `_warnings` SHALL contain one entry per failed source
**AND** the SPA Proposals row SHALL render an empty state with a warning chip

#### Scenario: Source timeout produces github_timeout warning

**WHEN** a `github:` source's REST request exceeds the per-source 10s timeout
**THEN** the response SHALL include `_warnings: [{source: "github:owner/repo", error: "github_timeout"}]`
**AND** the surviving sources' proposals SHALL still be returned
**AND** the failed source SHALL be retried on the next request (no circuit breaker)

---

### Requirement: GitHub API Request Budget Cap

Each `github:` source request SHALL impose a per-source request budget cap of 50 directory listings per refresh. The endpoint SHALL count GitHub REST calls per source (the initial `/contents/openspec/changes/` call plus any per-change-id recursion for branch/diff probing). If a source exceeds 50 calls in a single refresh, the endpoint SHALL truncate the result at the 50-call boundary AND emit a `_warnings` entry: `{source: "github:owner/repo", error: "github_budget_exceeded", message: "<N> changes truncated"}`.

This protects against runaway calls when a repo has many in-flight changes AND/OR when the per-change-id branch probe recursion expands the call count unexpectedly. 50 is the v1 default; the cap SHALL be configurable via a `OPENSPEC_SOURCES_GITHUB_CAP` env var (integer, default 50, max 5000 — GitHub's authenticated rate-limit).

The truncation behavior SHALL be deterministic: changes are sorted alphabetically by directory name before processing, so the same 50 changes are returned on every refresh until either the cap is raised or the repo's change set shrinks below the cap.

A future change MAY replace REST with a GraphQL batch query (one API call covering the full directory listing + branch state for N changes), which would remove the need for this cap. The cap MUST remain in place for the REST path regardless.

#### Scenario: Source within budget returns all changes

**WHEN** a github source has 30 changes in `openspec/changes/` AND the budget is 50
**THEN** all 30 changes SHALL be returned
**AND** no `github_budget_exceeded` warning SHALL be emitted

#### Scenario: Source exceeds budget returns truncated result

**WHEN** a github source has 80 changes AND the budget is 50
**THEN** the response SHALL include 50 proposals from that source (alphabetically first by `change_id`)
**AND** `_warnings` SHALL contain `{source: "github:owner/repo", error: "github_budget_exceeded", message: "30 changes truncated"}`

#### Scenario: Budget cap configurable via env var

**WHEN** `OPENSPEC_SOURCES_GITHUB_CAP = "100"` AND a github source has 80 changes
**THEN** all 80 changes SHALL be returned
**AND** no `github_budget_exceeded` warning SHALL be emitted

---

### Requirement: Documentation Updates for Multi-Repository Support

`docs/kanban-viz/README.md` SHALL be extended to document:

- `OPENSPEC_SOURCES` env var syntax, including both source type prefixes and the lowercase-normalization behavior.
- Hybrid cache strategy semantics (local at boot, github lazy 60s, refresh busts both).
- The `repo:<owner>/<repo>` label convention for issues — including the casing normalization rule and the "first match wins" tie-breaker.
- The RepoBadge visual treatment and `hidden_repos` saved-view field.
- The degraded-mode `_warnings` behavior and the Proposals row partial-result chip.
- The `OPENSPEC_SOURCES_GITHUB_CAP` env var and its default value.
- A cross-link to the PR #211 `GITHUB_REPOS` documentation so the parallel multi-repo pattern is discoverable from either entry point.

#### Scenario: README documents OPENSPEC_SOURCES alongside GITHUB_REPOS

**WHEN** an operator reads `docs/kanban-viz/README.md` after this change lands
**THEN** the "Environment Variables" section SHALL include `OPENSPEC_SOURCES` with syntax examples for both `local:` and `github:` entries
**AND** a cross-link SHALL point to the `GITHUB_REPOS` section to highlight the parallel pattern
