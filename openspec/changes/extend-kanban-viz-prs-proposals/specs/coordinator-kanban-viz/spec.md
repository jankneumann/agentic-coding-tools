# coordinator-kanban-viz Spec Delta — extend-kanban-viz-prs-proposals

This delta extends the existing `coordinator-kanban-viz` spec with PR + Proposal projections, refresh-button semantics, source swimlanes, and cluster collapse. All new requirements are ADDED. No existing requirement is MODIFIED or REMOVED — the discriminated-union refactor on the SPA side is an internal implementation evolution that preserves every behavior captured by the existing requirements (Issue cards still render the same way, sync-point banner is untouched, save-views still persist, SSE stream continues unchanged).

## ADDED Requirements

### Requirement: New Coordinator Endpoint — Open Pull Requests

The coordinator SHALL expose `GET /github/prs` returning all open pull requests across the configured repositories, classified by origin, sorted newest-first by `updated_at` descending.

The response SHALL be a JSON object with shape `{prs: PRCard[], generated_at_iso: string, source: "live" | "cache", cache_age_seconds: integer}`. Each `PRCard` SHALL contain at minimum: `kind: "pr"` (literal), `id` (string, of the form `pr:<repo>:<number>`), `change_id` (string or null — extracted from the head branch when it matches `openspec/<id>` or `claude/<id>` per the established classification rules in `discover_prs.py`), `repo` (string `<owner>/<name>`), `number` (integer), `title` (string), `author` (string), `head_branch` (string), `base_branch` (string), `origin` (string, one of `openspec / codex / jules / dependabot / renovate / manual`), `status` (string, one of `draft / open / review / changes_requested / approved`), `review_summary` ({`state`: string, `reviewer_count`: integer, `last_reviewed_at_iso`: string|null}), `is_draft` (boolean), `url` (string), `created_at_iso` (string), `updated_at_iso` (string).

The endpoint SHALL apply a 60-second in-memory cache shared across concurrent requests (single-flight). Clients SHALL be able to bust the cache by including `?refresh=true`. When the cache is fresh, `source` SHALL equal `"cache"` and `cache_age_seconds` SHALL be the integer seconds since the cached entry was minted; otherwise `source` SHALL equal `"live"` and `cache_age_seconds` SHALL be `0`.

The endpoint SHALL reuse the classification logic from `skills/merge-pull-requests/scripts/discover_prs.py` — that logic SHALL be extracted into a coordinator-importable module (`agent-coordinator/src/github_classifier.py` or equivalent) without duplicating its rules. The skill SHALL continue to import the same module so the classification stays single-sourced.

The classifier's native return surface includes fine-grained Jules sub-types (`sentinel`, `bolt`, `palette`) and a generic `other` fallback. For the `PRCard.origin` field, the coordinator endpoint SHALL fold these to the six-value `Origin` enum exposed in the contract: `sentinel | bolt | palette | jules → "jules"`, `other → "manual"`. This mapping SHALL live in a single helper (`to_pr_card_origin`) co-located with `classify_pr` so the skill — which needs the fine-grained sub-types for merge-strategy decisions — keeps the raw values, while the kanban-viz surface stays UI-stable at six chips. Future change widening the enum SHALL update both ends in lockstep.

The endpoint SHALL fail closed when the GitHub credential is absent: when `GITHUB_PAT` is unset (or no equivalent credential is available), `GET /github/prs` SHALL respond `503 Service Unavailable` with body `{error: "github_pat_missing", message: <string>}` and SHALL NOT shell out, NOT call the GitHub API, and NOT populate the cache.

The endpoint SHALL respond `200 OK` with an empty `prs: []` array — not 404, not 500 — when there are zero open PRs across the configured repositories.

#### Scenario: Endpoint returns PRs sorted newest-first

**WHEN** a client calls `GET /github/prs` and three open PRs exist with `updated_at` values `2026-06-10T10:00:00Z`, `2026-06-08T09:00:00Z`, `2026-06-09T11:00:00Z`
**THEN** the response `prs` array SHALL contain those three entries
**AND** their order SHALL be `2026-06-10`, `2026-06-09`, `2026-06-08` (descending by `updated_at`)
**AND** each entry SHALL include all the fields listed above

#### Scenario: Repeated calls within 60 seconds return cached data

**WHEN** a client calls `GET /github/prs` at T=0 and again at T=30 seconds without `?refresh=true`
**THEN** both responses SHALL be byte-identical except for `cache_age_seconds`
**AND** the second response's `source` SHALL equal `"cache"`
**AND** the second response's `cache_age_seconds` SHALL be approximately `30`
**AND** the GitHub API SHALL have been called exactly once

#### Scenario: refresh=true busts the cache

**WHEN** a client calls `GET /github/prs?refresh=true` 30 seconds after a fresh cache fill
**THEN** the cache SHALL be invalidated AND a new GitHub API call SHALL be made
**AND** the response's `source` SHALL equal `"live"`

#### Scenario: Missing GITHUB_PAT fails closed

**WHEN** the coordinator boots with `GITHUB_PAT` unset AND a client calls `GET /github/prs`
**THEN** the response status SHALL be `503`
**AND** the response body SHALL include `{"error": "github_pat_missing"}`
**AND** no outbound GitHub API call SHALL be made

#### Scenario: change_id is derived from branch name

**WHEN** a PR has `head_branch = "openspec/extend-kanban-viz-prs-proposals"`
**THEN** the resulting `PRCard.change_id` SHALL equal `"extend-kanban-viz-prs-proposals"`

**WHEN** a PR has `head_branch = "claude/fix-branch-mismatch-9P9o1"` AND PR body contains the line `Implements OpenSpec: fix-branch-mismatch`
**THEN** the resulting `PRCard.change_id` SHALL equal `"fix-branch-mismatch"` (claude/ branches classify as `openspec` per `feedback_claude_branch_classification.md`, but `change_id` is sourced from the body marker because the branch slug carries a random suffix like `-9P9o1` per `discover_prs.py:_extract_change_id_from_body`)

**WHEN** a PR has `head_branch = "claude/cloud-session-abc"` AND PR body has no `Implements OpenSpec:` line
**THEN** the resulting `PRCard.origin` SHALL still equal `"openspec"` (classifier rule)
**AND** the resulting `PRCard.change_id` SHALL be `null` (no body marker to source from)

**WHEN** a PR has `head_branch = "dependabot/npm_and_yarn/lodash-4.17.21"`
**THEN** the resulting `PRCard.change_id` SHALL be `null`

#### Scenario: Jules sub-types fold to a single origin on the PR card

**WHEN** the underlying classifier returns `origin = "sentinel"`, `origin = "bolt"`, or `origin = "palette"` (Jules sub-types from `JULES_PATTERNS`)
**THEN** the resulting `PRCard.origin` SHALL equal `"jules"` for all three
**AND** the skill's own `discover_prs.py` output SHALL still receive the fine-grained sub-type (kanban-viz fold is endpoint-local)

#### Scenario: Unrecognized origin folds to manual

**WHEN** the underlying classifier returns `origin = "other"`
**THEN** the resulting `PRCard.origin` SHALL equal `"manual"`

---

### Requirement: GitHub REST → Classifier-Shape Adapter

The endpoint SHALL translate every GitHub REST PR payload through a dedicated `from_rest_pr(rest_payload: dict) -> dict` adapter BEFORE feeding it into the classifier. The classifier (`classify_pr` in `agent-coordinator/src/github_classifier.py`, extracted from `discover_prs.py`) reads `gh` CLI JSON field names (`headRefName`, `body`, `title`, `labels[].name`, `author.login`, `createdAt`, `isDraft`, `url`), but the `GET /github/prs` endpoint fetches PRs via the GitHub REST API (per design D1), which returns DIFFERENT field names (`head.ref`, `user.login`, `created_at`, `draft`, `html_url`). The endpoint SHALL NOT pass raw REST payloads into the classifier — doing so silently sets `headRefName = ""`, which causes every PR to fall through to `origin = "other"` and `change_id = null`, defeating the entire single-source-classifier design.

The adapter SHALL live alongside the classifier in `agent-coordinator/src/github_classifier.py` (or a dedicated `github_rest_adapter.py` co-located there). The skill (`discover_prs.py`) SHALL continue to feed `gh`-CLI payloads directly to `classify_pr` without going through the adapter (gh-CLI shape is already canonical for the skill).

The translation MUST cover: `headRefName ← head.ref`, `body ← body`, `title ← title`, `labels ← labels` (already a list of `{name, ...}` in both shapes), `author ← {"login": user.login}` (the classifier's `safe_author` reads `pr["author"]["login"]`), `isDraft ← draft`, `createdAt ← created_at`, `updatedAt ← updated_at`, `url ← html_url`, `number ← number`, `baseRefName ← base.ref`.

#### Scenario: REST PR with openspec branch classifies correctly after adapter

**WHEN** a REST payload `{"head": {"ref": "openspec/foo"}, "user": {"login": "alice"}, "labels": [], "body": "", "title": "foo", "draft": false, "html_url": "https://github.com/...", "number": 1, "base": {"ref": "main"}, "created_at": "2026-06-10T00:00:00Z", "updated_at": "2026-06-10T01:00:00Z"}` is processed
**THEN** `from_rest_pr` SHALL produce `{"headRefName": "openspec/foo", "author": {"login": "alice"}, ...}`
**AND** `classify_pr(adapted)` SHALL return `{"origin": "openspec", "change_id": "foo"}` (NOT `"other"`/`null`)

#### Scenario: Adapter omission is detected by unit test

**WHEN** the endpoint module imports `classify_pr` but does NOT import `from_rest_pr`
**THEN** a static check (or dedicated unit test) SHALL fail with a clear message naming the missing adapter, preventing the silent-mis-classification regression

---

### Requirement: PRCard.status Derivation

The endpoint SHALL derive `PRCard.status` from the GitHub REST `isDraft` field and the projected `review_summary.state` using these deterministic rules, evaluated in order:

1. If `is_draft == true` → `status = "draft"`.
2. Else if `review_summary.state == "changes_requested"` → `status = "changes_requested"`.
3. Else if `review_summary.state == "approved"` AND every active reviewer's latest non-dismissed review is `APPROVED` → `status = "approved"`.
4. Else if `review_summary.state == "commented"` OR there exists at least one non-dismissed review of any state → `status = "review"`.
5. Else → `status = "open"`.

The precedence (changes_requested > approved > review > open) reflects the operator's question "what's blocking merge?" — `changes_requested` is more urgent than `approved`, so it wins even if a later reviewer approved.

#### Scenario: Draft PR with no reviews

**WHEN** the REST payload has `draft: true` AND no reviews exist
**THEN** `PRCard.status` SHALL equal `"draft"`

#### Scenario: PR with changes_requested wins over a later approval

**WHEN** the PR has reviews `[alice:approved@T-2h, bob:changes_requested@T-1h]` AND `is_draft = false`
**THEN** `PRCard.status` SHALL equal `"changes_requested"` (NOT `"approved"`)

#### Scenario: PR with all reviewers approved

**WHEN** the PR has reviews `[alice:approved@T-2h, bob:approved@T-1h]` AND `is_draft = false`
**THEN** `PRCard.status` SHALL equal `"approved"`

#### Scenario: PR with one comment

**WHEN** the PR has reviews `[alice:commented@T-1h]` AND `is_draft = false`
**THEN** `PRCard.status` SHALL equal `"review"`

#### Scenario: PR with no reviews and not draft

**WHEN** the PR has zero reviews AND `is_draft = false`
**THEN** `PRCard.status` SHALL equal `"open"`

---

### Requirement: GITHUB_REPOS Configuration

The endpoint SHALL read its repository allow-list from the `GITHUB_REPOS` environment variable. The value SHALL be a comma-separated list of `<owner>/<repo>` strings (e.g. `jankneumann/agentic-coding-tools,jankn/another-repo`). When unset, the endpoint SHALL default to a single hardcoded repository: `jankneumann/agentic-coding-tools` (the canonical home of this codebase).

The endpoint SHALL validate the env var on first request: each entry MUST match the regex `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`. An invalid entry SHALL cause the endpoint to respond `503` with body `{"error": "github_repos_invalid", "message": "<offending entry>"}` rather than partial results. Validation SHALL be cached alongside the PR cache.

When multiple repos are configured, the endpoint SHALL fan out concurrent fetches (capped at the same 20-concurrent limit as the per-PR reviews fetch) and concatenate results before sort. The `repo` field on each `PRCard` SHALL distinguish them.

#### Scenario: Default repo when GITHUB_REPOS unset

**WHEN** the coordinator boots with `GITHUB_REPOS` unset AND `GITHUB_PAT` set
**THEN** the endpoint SHALL fetch from `jankneumann/agentic-coding-tools` only
**AND** all returned `PRCard.repo` values SHALL equal `"jankneumann/agentic-coding-tools"`

#### Scenario: Invalid GITHUB_REPOS entry fails closed

**WHEN** `GITHUB_REPOS = "valid/repo,not_a_valid_entry"` AND a client calls `GET /github/prs`
**THEN** the response status SHALL be `503`
**AND** the response body SHALL include `{"error": "github_repos_invalid"}`
**AND** no outbound GitHub API call SHALL be made

---

### Requirement: New Coordinator Endpoint — OpenSpec Proposals Projection

The coordinator SHALL expose `GET /openspec/proposals` returning every change directory under `openspec/changes/` that is not under `archive/`, classified by implementation state derived from the corresponding git branch.

The response SHALL be a JSON object with shape `{proposals: ProposalCard[], generated_at_iso: string, source: "live" | "cache", cache_age_seconds: integer}`. Each `ProposalCard` SHALL contain at minimum: `kind: "proposal"` (literal), `id` (string, equal to `proposal:<change-id>`), `change_id` (string), `title` (string — extracted from the first H1 of `proposal.md`), `status` (string, one of `drafted / in-impl` — archived proposals are excluded by definition and never returned), `created_at_iso` (string — `proposal.md` git first-commit time), `updated_at_iso` (string — most recent commit time touching the change directory), `proposal_path` (string), `has_tasks_md` (boolean), `has_design_md` (boolean), `has_spec_delta` (boolean), `has_branch` (boolean), `branch_name` (string or null), `code_changes_outside_proposal` (integer — number of commits on the branch whose diff touches paths outside `openspec/changes/<change-id>/`).

A proposal SHALL be classified `in-impl` when ALL of the following are true: (1) a branch named `openspec/<change-id>` exists locally OR on the configured remote, AND (2) `code_changes_outside_proposal >= 1`. Otherwise the status SHALL be `drafted` (archive entries are excluded by definition).

The endpoint SHALL apply the same 60-second in-memory cache + `?refresh=true` bust pattern as `GET /github/prs`. The `source` and `cache_age_seconds` fields SHALL have the same semantics.

The endpoint SHALL operate from the coordinator's local checkout of the repository — it SHALL NOT call the GitHub API for this projection. The branch-existence and commit-diff probes SHALL use the local git index and refs only; remote tracking branches SHALL be considered "exists" without invoking `git fetch`.

The endpoint SHALL respond `200 OK` with an empty `proposals: []` array when no change directories exist outside `archive/`.

The endpoint SHALL be resilient to malformed change directories: a change directory missing `proposal.md` SHALL be omitted from the response (NOT cause a 500), and a warning SHALL be logged.

The endpoint SHALL fail closed when `.git` is unavailable in the runtime checkout: `git rev-parse --git-dir` is invoked at request time; on non-zero exit (typical of Docker `COPY` layers that omit `.git`), the endpoint SHALL respond `503 Service Unavailable` with body `{"error": "git_unavailable", "message": <string>}` and SHALL NOT walk the changes tree. This matches the `GET /github/prs` fail-closed posture (missing `GITHUB_PAT` → 503) so the SPA can surface a single per-row "feature unavailable in this deployment" chip pattern.

#### Scenario: Endpoint fails closed when .git is missing

**WHEN** the coordinator's runtime checkout has no `.git` directory (e.g., Docker `COPY` omitted it) AND a client calls `GET /openspec/proposals`
**THEN** the response status SHALL be `503`
**AND** the response body SHALL include `{"error": "git_unavailable"}`
**AND** the endpoint SHALL NOT walk `openspec/changes/`

#### Scenario: Endpoint enumerates non-archive change directories

**WHEN** the repository has `openspec/changes/foo/proposal.md`, `openspec/changes/bar/proposal.md`, AND `openspec/changes/archive/baz/proposal.md`
**THEN** the response `proposals` array SHALL contain exactly two entries, with `change_id` of `foo` and `bar`
**AND** no entry SHALL have `change_id = "baz"` or `change_id = "archive"`

#### Scenario: in-impl detection requires real code on the branch

**WHEN** change `foo` has branch `openspec/foo` whose diff vs. main touches only `openspec/changes/foo/proposal.md` and `openspec/changes/foo/tasks.md`
**THEN** the resulting `ProposalCard.status` SHALL equal `"drafted"`
**AND** `code_changes_outside_proposal` SHALL equal `0`

**WHEN** change `bar` has branch `openspec/bar` whose diff vs. main touches `openspec/changes/bar/proposal.md` AND `agent-coordinator/src/foo.py`
**THEN** the resulting `ProposalCard.status` SHALL equal `"in-impl"`
**AND** `code_changes_outside_proposal` SHALL be `>= 1`

#### Scenario: Branch absent ⇒ drafted

**WHEN** change `qux` has `openspec/changes/qux/proposal.md` but no `openspec/qux` branch exists locally or on remote
**THEN** the resulting `ProposalCard.status` SHALL equal `"drafted"`
**AND** `has_branch` SHALL be `false`
**AND** `branch_name` SHALL be `null`

#### Scenario: Malformed change directory is skipped

**WHEN** a directory `openspec/changes/orphan/` exists with no `proposal.md`
**THEN** the response SHALL omit any entry with `change_id = "orphan"`
**AND** the coordinator SHALL emit a warning-level log entry naming the orphan directory
**AND** the response SHALL still be `200 OK`

---

### Requirement: Polymorphic Board Card Model in SPA

The SPA SHALL model board cards as a discriminated union `BoardCard = IssueCard | PRCard | ProposalCard` discriminated on a `kind: "issue" | "pr" | "proposal"` literal field. The existing `Issue` interface in `apps/kanban-viz/src/lib/coordinator-types.ts` SHALL be renamed to `IssueCard` with a `kind: "issue"` field added. PR and proposal cards SHALL be added as siblings using the field shapes specified in the `GET /github/prs` and `GET /openspec/proposals` requirements above.

Every consumer of card data in the SPA SHALL narrow on `kind` before accessing kind-specific fields. TypeScript exhaustiveness SHALL be enforced via a default `never` branch in any switch on `card.kind`.

Per-kind status enums and column mappings SHALL be separate:
- `IssueCard.status: "pending" | "claimed" | "running" | "completed" | "failed" | "blocked"` — unchanged.
- `PRCard.status: "draft" | "open" | "review" | "changes_requested" | "approved"`.
- `ProposalCard.status: "drafted" | "in-impl"`. (Archived proposals are not returned by `GET /openspec/proposals`, so the SPA type does not need to model them.)

Three column-mapping functions SHALL exist: `issueStatusToColumn`, `prStatusToColumn`, `proposalStatusToColumn`, each returning `ColumnId`. The existing single `statusToColumn` SHALL be renamed to `issueStatusToColumn` and its behavior preserved.

Column mapping:
- Issues: `pending | blocked → backlog`, `claimed | running → in-flight`, `completed | failed → done`. This MUST be byte-identical to the existing `statusToColumn` implementation at `apps/kanban-viz/src/lib/coordinator-types.ts:48` — `issueStatusToColumn` is a rename, NOT a behavior change. Any deviation regresses the board's current behavior for blocked (currently shown as "needs attention" in backlog) and failed (currently terminal in done).
- PRs: `draft → backlog`, `open | review | changes_requested → in-flight`, `approved → done`. Merged PRs are not returned by `GET /github/prs` and therefore do not need a mapping.
- Proposals: `drafted → backlog`, `in-impl → in-flight`. Archived proposals are not returned by `GET /openspec/proposals` and therefore do not need a column.

#### Scenario: Discriminated union narrows in switch

**WHEN** the SPA code contains `switch (card.kind) { case "issue": ...; case "pr": ...; case "proposal": ...; }`
**THEN** TypeScript strict mode SHALL accept the switch without a default branch
**AND** removing any one case SHALL cause a TypeScript compile error in strict mode

#### Scenario: PR card maps to in-flight when status is review

**WHEN** `prStatusToColumn({ kind: "pr", status: "review", ... })` is invoked
**THEN** the return value SHALL equal `"in-flight"`

#### Scenario: Proposal card maps to backlog when status is drafted

**WHEN** `proposalStatusToColumn({ kind: "proposal", status: "drafted", ... })` is invoked
**THEN** the return value SHALL equal `"backlog"`

---

### Requirement: Source Swimlanes for Three Card Streams

The SPA SHALL render a `SourceSwimlanes` component that lays the board out as three rows × three columns. Rows SHALL correspond to card sources in this order (top to bottom): Issues, PRs, Proposals. Columns SHALL match the existing `backlog / in-flight / done` triple.

Each row SHALL render its source label in a left-rail header and SHALL display row-level totals (`<N> in backlog`, `<N> in flight`, `<N> done`) in the header.

Row visibility SHALL be toggleable via a header chip per source. The default SHALL be all three visible. Hidden rows SHALL persist via the existing saved-views mechanism.

`SourceSwimlanes` SHALL coexist with the existing `VendorSwimlanes` component on issue cards — vendor swimlanes apply within the Issues row only.

#### Scenario: All three rows render with totals

**WHEN** the board has 4 issues (2 backlog, 1 in-flight, 1 done), 3 PRs (0 backlog, 3 in-flight, 0 done), and 2 proposals (1 backlog, 1 in-flight, 0 done)
**THEN** the rendered DOM SHALL contain three row containers (Issues / PRs / Proposals) in that vertical order
**AND** the Issues row header SHALL show `2 backlog · 1 in flight · 1 done`
**AND** the PRs row header SHALL show `0 backlog · 3 in flight · 0 done`
**AND** the Proposals row header SHALL show `1 backlog · 1 in flight · 0 done`

#### Scenario: Hiding a row persists via saved view

**WHEN** the user clicks the "Proposals" chip to hide that row AND then saves the current view as `compact`
**THEN** subsequent reloads of saved view `compact` SHALL render with the Proposals row hidden
**AND** the saved view JSON SHALL include `{hidden_rows: ["proposals"]}` or equivalent

---

### Requirement: Refresh Button with Per-Source Last-Refreshed Timestamps

The SPA header SHALL include a `RefreshButton` that triggers a parallel refetch of all three sources (`/issues/list`, `/github/prs?refresh=true`, `/openspec/proposals?refresh=true`).

**Multi-change preservation**: The existing `useCoordinator` hook at `apps/kanban-viz/src/hooks/useCoordinator.ts` fetches issues for multi-change boards by POSTing `/issues/list` once per `changeId` and unioning the results (see `fetchIssuesUnioned`) — because the backend ANDs the labels filter, a single POST with multiple change_ids returns the empty intersection rather than the union. The new `useBoardCards` hook and the RefreshButton SHALL preserve this per-change parallel fetch + union semantics for issues. A single batched `/issues/list` call SHALL NOT replace the per-change fetch — doing so silently empties multi-change boards.

While a refresh is in flight, the button SHALL show a spinner state and SHALL be disabled to prevent double-submits.

Each source SHALL display its own last-refreshed-at timestamp (relative, e.g. `Issues · updated 12s ago`) in the row header. The timestamp SHALL update from the response's `generated_at_iso` field for PRs and proposals; for issues the timestamp SHALL be the wall-clock moment of the successful `/issues/list` response.

If any one source fails, the SPA SHALL surface a per-row error chip on that row only; the other two SHALL continue rendering successfully-refreshed data. The Refresh button SHALL return to its idle state when all three requests have resolved (success or failure).

#### Scenario: Refresh refetches all three sources in parallel

**WHEN** the user clicks the Refresh button
**THEN** the SPA SHALL initiate `POST /issues/list`, `GET /github/prs?refresh=true`, AND `GET /openspec/proposals?refresh=true` concurrently (not sequentially)
**AND** the button SHALL display a spinner state until all three resolve

#### Scenario: One source failing does not block the others

**WHEN** a refresh is in flight AND `GET /github/prs` returns 503 while the other two return 200
**THEN** the PR row SHALL display an error chip with a retry affordance
**AND** the Issues and Proposals rows SHALL update with their fresh data
**AND** the Refresh button SHALL return to idle (not stuck in spinner)

#### Scenario: Multi-change board refresh unions per-change issues

**WHEN** the board is configured with `changeIds = ["foo", "bar"]` AND the user clicks Refresh
**THEN** the SPA SHALL issue two POSTs to `/issues/list`, one with `{change_ids: ["foo"]}` and one with `{change_ids: ["bar"]}` (preserving the existing per-change fetch + union)
**AND** the resulting Issues row SHALL contain the union of issues from both change_ids
**AND** a single batched POST with `{change_ids: ["foo", "bar"]}` SHALL NOT replace this — that pattern returns the empty intersection per the backend's AND-on-labels semantics

---

### Requirement: Saved-View Schema Extension for Card-Source Fields

The coordinator's saved-view JSON schema at `agent-coordinator/src/schemas/kanban_viz/saved-view.json` SHALL be extended with two optional fields under `view`: `pr_origins` (array of origin strings, items matching the contract `Origin` enum) and `hidden_rows` (array, items one of `"issues" | "prs" | "proposals"`). Both fields SHALL be optional.

The schema currently sets `additionalProperties: false` on the `view` object, which would silently reject saved views containing the new fields — failing the persistence path with no clear surface. The schema update SHALL be made in lockstep with the SPA writes. Saved views written prior to this change SHALL continue to validate (the new fields are optional, not required).

#### Scenario: Saved view with pr_origins validates

**WHEN** the SPA writes a saved view with `view.pr_origins = ["openspec", "codex"]` AND `view.hidden_rows = ["proposals"]`
**THEN** the coordinator schema validator SHALL accept the document as valid
**AND** the persisted JSON SHALL round-trip via `PUT /kanban-viz/saved-views/{slug}` then `GET /kanban-viz/saved-views/{slug}` with both new fields intact

#### Scenario: Pre-existing saved view continues to validate

**WHEN** a saved view written before this change (with no `pr_origins` or `hidden_rows`) is loaded
**THEN** the schema validator SHALL accept it
**AND** the SPA SHALL fall back to the default selection (all origins, no hidden rows)

---

### Requirement: PR Origin Filter with Multi-Select Persistence

The SPA SHALL render an origin filter on the PR row toolbar as a multi-select chip group: `openspec / codex / jules / dependabot / renovate / manual`. The default SHALL be all origins selected.

Selecting/deselecting a chip SHALL filter `PRCard` rendering in real time without re-fetching from the coordinator (client-side filter on the already-loaded card array).

The selection state SHALL persist via the existing saved-views mechanism using a `pr_origins` field on the view payload. Loading a saved view SHALL restore the selection. The default view (no saved view active) SHALL retain selection across SPA reloads via `localStorage` under the key `kanban-viz:pr-origins`.

#### Scenario: Deselecting an origin hides matching cards

**WHEN** the PR row contains 3 cards with `origin = "openspec"` and 2 with `origin = "dependabot"` AND the user deselects the `dependabot` chip
**THEN** the PR row SHALL render exactly 3 cards
**AND** no `GET /github/prs` request SHALL be issued in response to the chip click

#### Scenario: Default-view selection persists across reloads

**WHEN** the user deselects `dependabot` AND reloads the SPA without saving a view
**THEN** on reload, the `dependabot` chip SHALL be deselected
**AND** `localStorage["kanban-viz:pr-origins"]` SHALL contain a serialization that excludes `dependabot`

---

### Requirement: Review-Findings Projection on PR Cards

Each `PRCard` SHALL render its `review_summary` inline on the card face. The rendering SHALL include: the latest review state (`approved` / `changes_requested` / `commented` / `none`), the reviewer count, and the relative time of the last review (e.g. `Approved · 2 reviewers · 4h ago`).

The visual treatment SHALL distinguish `changes_requested` (warning chrome) from `approved` (success chrome) from `commented`/`none` (neutral chrome). The chrome SHALL meet the existing accessibility contrast standard used elsewhere in the SPA.

The `review_summary.state` field SHALL be derived server-side in the coordinator from the GitHub reviews payload using the standard "last non-dismissed review per reviewer" reduction, with the following deterministic precedence (highest wins):

1. `changes_requested` — if ANY active reviewer's latest non-dismissed review is `CHANGES_REQUESTED`.
2. `approved` — if NO reviewer is at `changes_requested` AND at least one reviewer's latest is `APPROVED`.
3. `commented` — if NO reviewer is at `changes_requested` or `approved` AND at least one reviewer's latest is `COMMENTED`.
4. `none` — no non-dismissed reviews exist.

**Coherence with `PRCard.status`**: The `PRCard.status` ladder (`draft > changes_requested > approved > review > open`) and the `review_summary.state` ladder are designed to NOT contradict each other in the operator's mental model. Specifically, when `review_summary.state = "approved"` but `PRCard.status = "review"` (e.g., one approval + one comment from distinct reviewers), the card SHALL show success-chrome on the review-summary chip AND in-flight column placement — both are correct: an approval was given, but the PR is still in active review because not every reviewer has approved. The two surfaces complement rather than contradict; this is documented behavior, not a bug.

This logic SHALL be unit-tested at the coordinator with at least the five scenarios below.

#### Scenario: PR with two approvals and one changes_requested → changes_requested wins

**WHEN** a PR has reviews `[alice:approved@T-2h, bob:changes_requested@T-1h, alice:approved@T-3h]`
**THEN** the resulting `review_summary.state` SHALL equal `"changes_requested"`
**AND** `reviewer_count` SHALL equal `2`
**AND** `last_reviewed_at_iso` SHALL correspond to the `bob:changes_requested` event (the most recent)

#### Scenario: PR with no reviews

**WHEN** a PR has zero reviews
**THEN** `review_summary.state` SHALL equal `"none"`
**AND** `reviewer_count` SHALL equal `0`
**AND** `last_reviewed_at_iso` SHALL be `null`

#### Scenario: Dismissed reviews are excluded

**WHEN** a PR has reviews `[alice:changes_requested@T-2h dismissed, alice:approved@T-1h]`
**THEN** `review_summary.state` SHALL equal `"approved"`
**AND** `reviewer_count` SHALL equal `1`

#### Scenario: Approved + commented from distinct reviewers — approved wins

**WHEN** a PR has reviews `[alice:approved@T-2h, bob:commented@T-1h]` AND `is_draft = false`
**THEN** `review_summary.state` SHALL equal `"approved"` (approved beats commented in the precedence ladder)
**AND** `reviewer_count` SHALL equal `2`
**AND** the resulting `PRCard.status` SHALL equal `"review"` (NOT `"approved"`) — because the PRStatus ladder's "approved" rung requires EVERY reviewer's latest to be `APPROVED`, and bob's latest is `commented`. The review-summary chip shows success-chrome (state = approved); the column placement is in-flight (status = review). Both are correct per their respective ladders; the two surfaces complement rather than contradict.

---

### Requirement: Same-change_id Clustering with Expand Affordance

When multiple cards across rows share the same `change_id`, the SPA SHALL render a visual cluster indicator linking them. Default behavior SHALL be: the cards remain in their respective rows (cluster does NOT collapse rows into a single card), but each card SHALL render a cluster badge that, on hover, shows the change_id and the count of related cards across rows. Clicking the badge SHALL highlight all sibling cards (same change_id) with a temporary outline.

This requirement intentionally specifies a non-collapsing cluster indicator rather than a single merged card, because the user value is "see cross-source state at a glance" — collapsing into one card would hide the per-source status the user came to see.

#### Scenario: Three cards share a change_id render a cluster badge

**WHEN** the board contains an `IssueCard`, `PRCard`, and `ProposalCard` all with `change_id = "extend-kanban-viz-prs-proposals"`
**THEN** each of the three cards SHALL render a cluster badge showing `3` or equivalent indicator
**AND** hovering the badge SHALL display a tooltip naming the change_id

#### Scenario: Click highlights siblings

**WHEN** the user clicks the cluster badge on the issue card sharing change_id `foo`
**THEN** the PR card and proposal card with change_id `foo` SHALL each render a temporary outline (≥ 1.5s)
**AND** the highlight SHALL be visually distinct from selection/focus state

#### Scenario: Card with no change_id does not render a cluster badge

**WHEN** a `PRCard` has `change_id = null` (e.g., a Dependabot PR)
**THEN** that card SHALL NOT render a cluster badge
**AND** no clustering computation SHALL include that card

---

### Requirement: Documentation for PR and Proposal Endpoints

`docs/kanban-viz/README.md` SHALL document the two new endpoints (`GET /github/prs`, `GET /openspec/proposals`), the `GITHUB_PAT` and `GITHUB_REPOS` env-var posture, the refresh-button semantics (60s cache, `?refresh=true` bust), the per-row last-refreshed timestamps, and the cluster badge interaction.

The `apps/kanban-viz/.env.example` file SHALL document the existing `VITE_COORDINATOR_URL`, `VITE_COORDINATOR_API_KEY`, and `VITE_CHANGE_IDS` env vars (precondition; covered separately on the parent branch but referenced here for completeness).

#### Scenario: README lists all coordinator endpoints

**WHEN** an operator reads `docs/kanban-viz/README.md`
**THEN** the "Coordinator Endpoints Used" table SHALL contain rows for `GET /github/prs` and `GET /openspec/proposals` alongside the existing rows
