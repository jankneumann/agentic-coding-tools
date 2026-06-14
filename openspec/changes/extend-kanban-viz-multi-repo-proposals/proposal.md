# Extend Kanban Viz to Multiple Repositories

## Why

PR #211 (extend-kanban-viz-prs-proposals) shipped the kanban-viz with three
card sources — Issues, PRs, Proposals — but only PRs are multi-repo today
(`GITHUB_REPOS` env var, fan-out fetch). Proposals are scoped to the
coordinator's local checkout; issues are repo-agnostic but unsurfaced as such.

Operationally, this matters because the user's actual workflow now spans
multiple owned repositories: `agentic-coding-tools`, `newsletter-aggregator`,
`agentic-assistant`, and others. Work in one repository routinely produces
feedback that influences another (a Langfuse pattern discovered in one repo
gets ported into another; a bug fix in agentic-coding-tools' coordinator
unblocks features in agentic-assistant). The board currently can't visualize
this cross-pollination because:

- The Proposals row shows ONLY the coordinator's own `openspec/changes/`,
  not proposals in any other repo.
- The Issues row hides which repo each issue belongs to.
- Cluster badges key on bare `change_id`, so identical change-ids across
  repos (a real risk — `fix-auth` is generic) would falsely link unrelated
  work, OR cross-repo influence stays invisible because clusters only
  trigger when entities live in the same repo.

The goal is a single board that surfaces the *whole* personal pipeline
state across all owned repos, with clear per-repo attribution and safe
cross-repo cluster keying.

## What Changes

### Coordinator (`agent-coordinator/`)

- **NEW** `OPENSPEC_SOURCES` env var (CSV, parallel to `GITHUB_REPOS`).
  Each entry is either `local:/path/to/checkout` (filesystem walk) or
  `github:<owner>/<repo>` (GitHub REST API via the existing `GITHUB_PAT`).
  Default: empty (current single-checkout behavior).
- **CHANGED** `GET /openspec/proposals` — fans out across all configured
  sources concurrently, merging results. Each `ProposalCard` now carries
  a `repo` field (`<owner>/<repo>` for github sources; basename of the
  checkout directory or a configured alias for local sources) and a
  `change_id_namespaced` field equal to `<repo>/<change-id>`.
- **NEW** Hybrid cache strategy (per Q1c): local sources walked eagerly at
  boot (sub-millisecond per source, deterministic); github sources cached
  lazily per-source with 60s TTL (parity with `GET /github/prs` cache).
  `?refresh=true` busts BOTH local re-walk AND github re-fetch.
- **NEW** Optional `repo` label convention on `work_queue` rows: labels
  prefixed `repo:<owner>/<repo>` are surfaced as `IssueCard.repo`. No
  schema migration — uses the existing `labels` array. Rows without the
  prefix keep `repo: null`.
- **CHANGED** `GET /issues/list` — response shape unchanged; the SPA
  derives `IssueCard.repo` client-side from the labels array.

### SPA (`apps/kanban-viz/`)

- **NEW** `ProposalCard.repo: string | null` and
  `ProposalCard.change_id_namespaced: string | null` fields in
  `coordinator-types.ts` (re-exported via `contracts/generated/types.ts`).
- **NEW** `IssueCard.repo?: string | null` (optional, client-derived from
  labels).
- **CHANGED** `clusterBoardCards` keys on `change_id_namespaced`
  (`<repo>/<change-id>`) when present, falling back to bare `change_id`
  only when `repo` is null on all cluster members (back-compat for
  pre-multi-repo data).
- **NEW** Per-card `RepoBadge` micro-component — small repo chip rendered
  on `IssueCardView`, `PRCardView`, `ProposalCardView`. Hidden when
  `repo: null`. Hover surfaces the full `<owner>/<repo>`.
- **NEW** Optional `hidden_repos: string[]` field in the saved-view
  schema, mirroring the `hidden_rows` + `pr_origins` pattern from
  PR #211. Hides all cards whose `repo` matches one of the listed repos.

### Documentation
- `docs/kanban-viz/README.md` — document `OPENSPEC_SOURCES` syntax,
  hybrid cache semantics, repo-label convention, repo badge, hidden-repos
  saved-view field. Cross-link from PR #211's `GITHUB_REPOS` doc so the
  parallel pattern is discoverable.

### Out of Scope
- **No federation across N coordinators.** This change ships single-
  coordinator multi-repo. Path B (federated kanban-viz) stays deferred
  until team-scale.
- **No cross-repo cluster registry.** Same-`change_id` cards in
  DIFFERENT repos do NOT cluster by default (Q2a). The optional
  registry that would override this — say, "change-id X in repo A is
  intentionally linked to change-id Y in repo B" — is documented as a
  future hook but not built.
- **No per-repo PAT rotation.** One `GITHUB_PAT`, multiple owned repos
  under the same identity (the user's personal scale framing).
- **No `work_queue` schema migration.** Repo qualification is via
  labels only; existing rows without `repo:` labels show `repo: null`
  on IssueCard.
- **No GitHub App migration.** PAT is sufficient for the read scopes
  needed (`/contents/openspec/changes/` is covered by the same
  `Pull requests: Read + Contents: Read` set documented for PR #211).
- **No write actions across repos.** The board still projects state;
  write actions (merge, dispatch, archive) remain in their respective
  skills.

## Approaches Considered

### Approach A — Direct extension (recommended)

Add `OPENSPEC_SOURCES` as a CSV env var parallel to `GITHUB_REPOS`. Walk
local sources at boot, fetch github sources lazily on first request with
per-source 60s cache slots. Extend the existing `ProposalCard` and
`IssueCard` types with optional `repo` fields. Change `clusterBoardCards`
to key on `change_id_namespaced` when present, falling back to bare
`change_id` for back-compat. Use the existing label convention
(`repo:<owner>/<repo>`) for issue repo attribution — no schema migration.
Add a `RepoBadge` micro-component and a `hidden_repos` saved-view field.

**Pros**:
- Strictly additive — no breaking changes to PR #211's wire contracts,
  no migrations, no version bumps. Existing single-repo boards stay
  identical (repo-less cards still cluster on bare `change_id`).
- Mirrors the `GITHUB_REPOS` pattern that PR #211 already proved out;
  operators learn one mental model that applies to all three streams.
- Label-based issue repo attribution is consistent with the existing
  saved-view extension pattern (optional additive fields, no schema
  version bump).
- Small surface area — estimated ~3 packages × 400 LOC each, much
  smaller than PR #211 because the polymorphic card model already
  exists.

**Cons**:
- The label convention is a *convention*, not enforced — agents could
  emit `repo:` labels with inconsistent capitalization or
  `repo:org/Repo` vs `repo:org/repo`. Need normalization at the
  client-side derivation step.
- Hybrid cache strategy doubles the cache implementation complexity
  (local-source warmup needs a separate code path from github-source
  TTL slots). Mitigation: both paths share the same response shape;
  only the cache key/warmup differs.
- `change_id_namespaced` fallback semantics need explicit
  documentation: when EITHER cluster member has `repo: null`, the
  cluster falls back to bare `change_id`. This is back-compat for
  pre-multi-repo data but easy to mis-explain.

**Effort**: M (≈ 1.5 days coordinator + ≈ 1 day SPA + tests).

### Approach B — Unified `SourceDescriptor` abstraction

Introduce a `SourceDescriptor` Pydantic model (`{repo, kind, base_url}`)
that becomes the canonical input to all three endpoints (`/issues/list`,
`/github/prs`, `/openspec/proposals`). Each card kind gets a generic
`source: SourceDescriptor` field replacing the existing per-kind `repo`
field. Cluster on a generic `cluster_key` field computed server-side.
Push the `OPENSPEC_SOURCES` and `GITHUB_REPOS` env vars under a single
unified config block.

**Pros**:
- Architecturally cleaner — one abstraction for "where does this card
  come from", consistent across all three streams.
- Future cross-repo cluster registry would slot in as a single
  `cluster_key` override layer, not three.
- Long-term: if Path B (federated) ever ships, the `SourceDescriptor`
  already carries enough information to know which coordinator a card
  came from.

**Cons**:
- BREAKING change to PR #211's `PRCard.repo` field shape, requires a
  SPA-side migration, and any external consumer of `/github/prs`
  (none today, but the contract is public-facing) breaks.
- Touches `/issues/list` more invasively than Approach A — every issue
  consumer learns the new `source` shape even when repo isn't relevant.
- Effort balloons because of the cross-cutting refactor; estimated
  ~2x Approach A in LOC and review effort.
- Speculative future-proofing: the `SourceDescriptor` is shaped for
  Path B (federation) which the user has explicitly deferred. Building
  for a deferred future tends to bias the design wrong.

**Effort**: L (≈ 3 days, plus a separate PR #211-style migration plan).

### Selected Approach

**Approach A — Direct extension.** Confirmed by user at Gate 1, with
the latent-intent check resolved: the goal "see all my work across all
my repos in one place" is delivered directly by A — every card kind
carries a `repo` field, every stream is multi-repo, clusters key on
`<repo>/<change-id>`, and `hidden_repos` provides per-repo focus mode.

Load-bearing commitments derived from this selection plus implementation
open-question defaults:

- `OPENSPEC_SOURCES` env var CSV, `local:<path>` and `github:<owner>/<repo>`
  source-type prefixes. Empty default = current single-source behavior.
- Hybrid cache: local sources at boot, github sources lazy with 60s TTL
  per source. `?refresh=true` busts both.
- Cluster key = `<repo>/<change-id>` when present, bare `change_id`
  fallback only when every cluster member has `repo: null`.
- `IssueCard.repo` derived client-side from the first `repo:<owner>/<repo>`
  entry in the issue's labels array. No `work_queue` schema migration.
- `repo:` label normalization: lowercase (matches GitHub's case-insensitive
  lookup).
- Local-source `repo` derivation: `git remote get-url origin` parsed for
  `owner/repo`; fall back to checkout basename with a warning log.
- GitHub API path: REST for v1 with a per-source request budget cap of
  ≤ 50 changes per refresh. GraphQL batching deferred.

Approach B (unified `SourceDescriptor`) is rejected and not carried
forward; the speculative future-proofing for Path B (federation) doesn't
pay rent today, and breaking PR #211's `PRCard.repo` contract is too
expensive given downstream consumers (the SPA, merge-pull-requests
skill) are stabilizing.

### Recommendation (original)

**Approach A.** Path B's user has been explicitly deferred, so
B's architectural-purity wins don't pay rent today. Approach A respects
"strictly additive — no breaking changes" which is the single most
useful invariant when PR #211 just shipped and downstream consumers
(the SPA, the merge-pull-requests skill) are starting to stabilize on
the contracts. The label-based issue repo attribution is the same
optional-additive pattern PR #211 used for `pr_origins` and
`hidden_rows` — operators and the saved-view schema already understand
that idiom. Approach B is the right *eventual* architecture but should
land as a "v2 contract" change after at least one external consumer
asks for it.

## Decision Boundaries (from user discovery)

- **D1 (sources config):** `OPENSPEC_SOURCES` CSV env var, parallel to
  `GITHUB_REPOS`. Each entry is `local:<path>` or `github:<owner>/<repo>`.
  Default empty (current single-checkout behavior preserved). User
  scope: personal/small-team, single coordinator, multiple owned repos.

- **D2 (cache strategy — Q1c):** Hybrid. Local sources walked eagerly
  at boot (cheap, deterministic). GitHub sources cached lazily on
  first request, 60s TTL per source. `?refresh=true` busts BOTH local
  re-walk AND github re-fetch.

- **D3 (cluster key default — Q2a):** Namespaced. Cluster on
  `<repo>/<change-id>` when `repo` is set on every member of the
  candidate cluster. Falls back to bare `change_id` only for the
  back-compat case where every member has `repo: null` (pre-multi-repo
  data). Cards in DIFFERENT repos with the same bare `change_id` do NOT
  cluster. Cross-repo cluster registry is a deferred future hook.

- **D4 (issue repo attribution — Q3b):** Label convention.
  `work_queue.labels` may include `repo:<owner>/<repo>` entries; the
  SPA derives `IssueCard.repo` from the first matching label.
  No schema migration. Issues without the label show `repo: null`
  and participate in clusters via the bare `change_id` fallback in D3.

- **D5 (auth):** Reuse existing `GITHUB_PAT` (per PR #211). One
  credential, all owned repos. Same fail-closed 503 posture on missing
  PAT applies to github-source proposal fetches.

- **D6 (degraded mode):** If one source in `OPENSPEC_SOURCES` is
  unreachable (e.g., the GitHub repo 404s, or a local path doesn't
  exist), the endpoint SHALL return the surviving sources with a
  per-source `_warnings: [{source, error}]` array in the response.
  The SPA SHALL surface a chip on the Proposals row indicating
  partial-result mode (similar to how PR #211 handles one-source-fails
  in the RefreshButton).

## Open Questions for Implementation

- **`repo:` label canonicalization:** Should the SPA reject
  `repo:Owner/Repo` (mixed case) or normalize it to lowercase? GitHub
  itself is case-preserving but case-insensitive on lookup; we'd want
  to match its behavior to avoid `repo:janKneumann/x` and
  `repo:jankneumann/x` producing two visual clusters.
- **Local-source `repo` derivation:** For `local:/path/to/checkout`,
  do we read `git remote get-url origin` to get the canonical
  `<owner>/<repo>`, or use the basename of the checkout directory?
  Origin URL is more accurate but adds a subprocess call per source at
  boot. Basename is simpler but fragile (rename the checkout, badge
  breaks). Default proposal: try origin URL first, fall back to
  basename with a warning.
- **GitHub-source rate limits:** Each github source costs ≥ 1
  `/contents/openspec/changes/` REST call per refresh, plus N calls
  if we recurse into each change-id directory for the `in-impl`
  detection. With multiple repos, this multiplies. Should we batch
  via the GraphQL API (one query for N repos) or stay on REST? Default
  proposal: REST for v1 with per-source request budget cap; GraphQL
  is a follow-up.
- **Cross-repo cluster registry shape:** Already deferred, but if we
  build it later, what's the registry source? A YAML file checked into
  the coordinator? A coordinator-table? A `change_id_aliases:` block
  in `openspec/project.md`? Defer the decision; this proposal just
  notes the override hook.
