# Design — extend-kanban-viz-multi-repo-proposals

## Context

PR #211 (extend-kanban-viz-prs-proposals) shipped a three-source kanban board (Issues, PRs, Proposals). Of the three, only PRs were multi-repo at launch via `GITHUB_REPOS`. This change extends multi-repo support to the remaining two streams (Proposals and Issues) under the personal/small-team scale framing the user confirmed: single coordinator, multiple owned repositories, one `GITHUB_PAT`.

The work is strictly additive on top of #211 — no breaking changes to the polymorphic card model, the `SourceSwimlanes` layout, the `useBoardCards` hook, the saved-view schema, or the `merge-pull-requests` skill's classifier import. The polymorphic `BoardCard` union already accommodates an optional `repo` field; we're adding it to the two card kinds that lacked it (`ProposalCard`, `IssueCard`), updating cluster keying to namespace, and adding a small `RepoBadge` component.

**File layout note (from PR #211 inspection):** `clusterBoardCards` lives INSIDE `apps/kanban-viz/src/hooks/useBoardCards.ts` (lines ~47–77), NOT at a standalone `apps/kanban-viz/src/lib/clusterBoardCards.ts`. All design references below to "cluster function changes" target that file. `coordinator-types.ts` correctly lives at `apps/kanban-viz/src/lib/coordinator-types.ts` and is the SPA's runtime copy of the contract types (the `openspec/changes/.../contracts/generated/types.ts` file is the spec source of truth; the SPA does not import from outside `apps/kanban-viz/src/` because `tsconfig.json` has `"include": ["src"]`).

## Goals / Non-Goals

### Goals

- Surface OpenSpec proposals from multiple repositories (local checkouts + GitHub-hosted) in one Proposals row.
- Surface issues from multiple repositories on one Issues row, attributed via a `repo:<owner>/<repo>` label convention.
- Cluster cards across the three streams ONLY when they share the same repository AND change-id, preventing false same-`change_id` collisions across repos.
- Preserve PR #211's single-source contracts: a coordinator booted without `OPENSPEC_SOURCES` set behaves byte-identically to the PR #211 version.
- Reuse the established multi-repo idiom (`GITHUB_REPOS`) so operators learn one mental model that applies to all three streams.

### Non-Goals

- **No federation across N coordinators.** Path B (kanban-viz fetches from many coordinator URLs) stays deferred until team-scale.
- **No cross-repo cluster registry.** Same change_id across different repos does NOT cluster by default; the registry that would change this is a future hook with a defined extension point but no implementation.
- **No `work_queue` schema migration.** Issue repo attribution is via the existing `labels` array — no new column, no alembic migration.
- **No per-repo PAT rotation, no per-team trust boundaries, no GitHub App migration.** Single PAT for all owned repos, per the user's personal-scale framing.
- **No write actions across repos.** The board projects state; write skills stay scoped to their repos.

## Decision Boundaries (from proposal Gate 1)

### D1 — `OPENSPEC_SOURCES` env var, parallel to `GITHUB_REPOS`

CSV with `local:<path>` and `github:<owner>/<repo>` entries. Empty default treats the coordinator's own checkout as an implicit `local:.` source — preserving PR #211 wire shape while ALSO deriving `ProposalCard.repo` from the coordinator's own `git remote get-url origin`. This keeps PR↔Proposal cross-row clustering working in single-source mode, because `PRCard.repo` (from `GITHUB_REPOS`) and `ProposalCard.repo` (from origin) lowercase-normalize to the same string.

**Why:** Operators already understand `GITHUB_REPOS` from PR #211. A parallel-named env var lets them apply the same mental model to the second endpoint without learning new config shape.

**Alternative considered:** Single unified env var `KANBAN_REPOS=owner/repo,owner/other-repo` that drives BOTH `GET /github/prs` and `GET /openspec/proposals`. Rejected — couples two endpoints' configs, and the proposals endpoint also wants `local:` paths (which the PRs endpoint doesn't), so the unification would leak abstraction holes.

### D2 — Hybrid cache strategy (per Q1c user answer)

Local sources walked eagerly at boot; GitHub sources cached lazily per-source with 60s TTL.

**Why:** Filesystem walks are sub-millisecond and deterministic — eager walking adds no boot latency worth measuring. GitHub REST calls are ~100–500ms each and rate-limited — lazy fetching with per-source TTL slots prevents amplification when N>3 GitHub repos are configured.

**Cache structure:**
- Local: single dict `{source: <walk-result>}`, written at boot and on `?refresh=true`.
- GitHub: dict `{source: (mint_time, cache_entry)}`, per-source mutex for single-flight (mirrors `github_prs_api.py`).
- Combined response field `source: "live" | "cache" | "mixed"` — note: `live` for a local source means "as-of-last-walk" (boot warmup OR most-recent `?refresh=true`), NOT re-walked per request. `cache_age_seconds` for local sources reflects time-since-last-walk and contributes to the MAX-across-sources worst-case freshness signal alongside github TTL ages. `mixed` indicates at least one local + at least one cached github source. (R1-009 clarification — earlier draft said "always live", which understated local-source staleness between refreshes.)

**Failure mode:** Local re-walks at boot run synchronously. If a `local:` path is unreachable at boot, the source is marked degraded in the source registry; subsequent requests skip it AND emit a `_warnings` entry — the boot doesn't crash. This matches D6's degraded-mode contract.

### D3 — Cluster key namespacing (per Q2a user answer)

`clusterBoardCards` keys on `change_id_namespaced = <repo>/<change-id>` when `repo` is set on every member; falls back to bare `change_id` only when EVERY member has `repo: null`.

**Why:** The user's actual scope is "see cross-pollination across my owned repos" — but they explicitly do NOT want incidental same-change_id collisions across unrelated repos producing visual confusion. The namespaced default is the safe path. The bare-fallback exists purely for back-compat with PR #211 single-source data (so coordinators booted without `OPENSPEC_SOURCES` continue to cluster correctly).

**Mixed-null edge case:** A cluster cannot mix `repo: null` and `repo: "x/y"` members. If a candidate cluster would mix, the function splits — repo-null group + one cluster per distinct repo. This is the only edge case worth a dedicated test.

**Future cross-repo registry hook:** The `clusterBoardCards` function will accept an optional `clusterKeyOverride: (card) => string | null` callback in its signature. The default callback implements the namespaced-with-fallback rule above. A future registry-driven extension would supply a different callback that maps cards via the registry's `change_id_aliases` table. No registry table is built in this change — only the override hook signature.

### D4 — Issue repo attribution via label convention (per Q3b user answer)

`work_queue.labels` array entries matching `^repo:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` are interpreted as repo qualifiers; SPA derives `IssueCard.repo` client-side from the first match.

**Why:** Label-based qualification is the same additive idiom PR #211 used for `pr_origins` and `hidden_rows` saved-view fields — optional, no schema version bump, no migration. Adding a `repo` column to `work_queue` would force a coordinated schema update across every consumer of `/issues/list`, with backward-compat fallbacks for existing rows that lack values. Labels avoid all of that.

**Normalization:** Lowercase only. GitHub itself is case-preserving but case-insensitive on lookup — matching its behavior prevents `repo:JanKneumann/x` and `repo:jankneumann/x` producing two visual clusters. Casing is normalized at derivation time (in the SPA), not at write time (in the coordinator) — the coordinator stays agnostic.

**First-match-wins tie-breaker:** When an issue has multiple `repo:` labels (operator error or intentional cross-tagging), the FIRST occurrence in the array wins. A browser-console warning is logged naming the issue id and the conflicting labels. This is a non-blocking surface so the operator can correct it without a hard error.

**Coordinator-side change:** None. The `/issues/list` response shape is unchanged. Derivation is pure SPA logic.

### D5 — Reuse `GITHUB_PAT` from PR #211

Single credential, all owned repos. The github-source proposal fetcher uses the same `httpx.AsyncClient` pattern and `Authorization: Bearer <GITHUB_PAT>` header as `github_prs_api.py`.

**Why:** The user's personal-scale framing makes this trivial — same identity owns all the repos. The 503 fail-closed posture from PR #211 (missing PAT → 503 with `{"error": "github_pat_missing"}`) extends naturally to this endpoint: when `OPENSPEC_SOURCES` contains a `github:` entry AND `GITHUB_PAT` is unset, the endpoint returns 503 — local-only sources continue to serve from cache, but mixed-mode fails closed.

**Fine-grained vs classic token:** Same scope guidance as PR #211 (classic `repo` or fine-grained `Pull requests: Read + Contents: Read`). The `/contents/openspec/changes/` API path is covered by `Contents: Read` — no additional scope needed beyond what PR #211 already requires.

### D6 — Degraded multi-source mode

Per-source failures (path missing, repo 404, PAT denied, timeout) surface as `_warnings` entries; surviving sources still serve. SPA renders Proposals row partial-result chip when `_warnings.length > 0`.

**Why:** With N > 1 sources configured, a single bad entry shouldn't break the whole row — that violates the user's "personal coordinator for multiple repos" use case (one bad repo = no visualization at all is unacceptable). The `_warnings` surface gives operators concrete error attribution.

**Per-source timeout:** 10s (vs the global request timeout, which inherits from the existing FastAPI/uvicorn config). The 10s budget is the longest any single GitHub REST call should plausibly take; longer is a network issue, not a "GitHub being slow."

**No circuit breaker:** Each refresh retries every configured source. The operator's mental model stays "refresh = try everything again" — adding a circuit breaker that pins a source as broken across requests would require operator-visible state management we don't want in v1.

### D7 — GitHub API request budget cap

Per-source budget of 50 directory listings per refresh, configurable via `OPENSPEC_SOURCES_GITHUB_CAP`.

**Why:** A repo with many in-flight OpenSpec changes plus per-change-id branch probe recursion could consume 100+ REST calls in a single refresh. With multiple repos configured, this multiplies. 50 is a deliberate ceiling that captures "typical personal-scale repo workload" (≤ 20 in-flight changes) with 2.5× headroom. The configurable cap lets power users opt into a higher limit if needed.

**Truncation behavior:** Alphabetical sort by `change_id` before processing, so the same 50 changes are returned on every refresh until the cap is raised or the repo's change set shrinks. Deterministic truncation prevents "different proposals on every refresh" jank.

**GraphQL alternative:** A future change could replace the REST fan-out with a single GraphQL query covering directory listing + branch state for N changes — that would eliminate the cap. Out of scope for this change; the cap stays in place for the REST path regardless.

## Implementation Plan Outline

### Coordinator side

**New module: `agent-coordinator/src/openspec_sources.py`**

Source-descriptor parsing + boot-time local-source warmup. Public surface:

```python
@dataclass(frozen=True)
class SourceDescriptor:
    kind: Literal["local", "github"]
    spec: str   # path for local, owner/repo for github (lowercase)
    repo: str   # derived <owner>/<repo> for label/cluster attribution

def parse_sources(env_val: str) -> tuple[list[SourceDescriptor], list[ParseWarning]]: ...
def warm_local_sources(sources: list[SourceDescriptor]) -> dict[str, LocalSourceCache]: ...
def derive_local_repo(path: Path) -> tuple[str, Optional[str]]:   # (repo, warning_if_any)
    """Try `git remote get-url origin` first; fall back to `local/<basename>`.

    The `local/` prefix on the basename fallback (R1-004) guarantees the
    derived repo value has owner/repo shape — so it passes the same regex
    used by GITHUB_REPOS, hidden_repos saved-view validation, and the
    namespaced cluster key. Without the prefix, a basename like
    'orphan-checkout' would fail downstream regex checks and produce
    inconsistent cluster keys.
    """
```

**Changed module: `agent-coordinator/src/openspec_proposals_api.py`**

The endpoint becomes source-aware. Pseudocode:

```python
async def list_proposals(refresh: bool = False) -> ProposalListResponse:
    sources = get_configured_sources()  # from openspec_sources.parse_sources

    if refresh:
        invalidate_local_walk_cache()
        invalidate_all_github_caches()

    proposals: list[ProposalCard] = []
    warnings: list[SourceWarning] = []
    statuses: list[Literal["live", "cache"]] = []

    # Local sources — already warm from boot, walk if invalidated
    for src in sources if src.kind == "local":
        try:
            walk, status = get_or_walk_local(src)
            proposals.extend(walk)
            statuses.append(status)
        except LocalSourceError as e:
            warnings.append(SourceWarning(source=src.spec, error=e.code))

    # GitHub sources — fan-out concurrent with single-flight mutex
    github_results = await asyncio.gather(*[
        fetch_github_source(src, refresh=refresh)
        for src in sources if src.kind == "github"
    ], return_exceptions=True)
    for src, result in zip(github_sources, github_results):
        if isinstance(result, BaseException):
            warnings.append(SourceWarning(source=src.spec, error=classify(result)))
        else:
            proposals.extend(result.proposals)
            statuses.append(result.status)

    return ProposalListResponse(
        proposals=proposals,
        _warnings=warnings,
        source=combine_status(statuses),  # live / cache / mixed
        cache_age_seconds=max_cache_age(statuses),
        generated_at_iso=now_iso(),
    )
```

**New module: `agent-coordinator/src/github_openspec_fetcher.py`**

Encapsulates GitHub REST calls for the proposals endpoint:

```python
async def fetch_proposals_from_github(
    source: SourceDescriptor,
    pat: str,
    budget: int = 50,
) -> tuple[list[ProposalCard], list[SourceWarning]]:
    """Fetch all proposals from a github source, respecting the budget cap."""
```

Uses the existing `httpx.AsyncClient` pattern with `Authorization: Bearer <PAT>` and `Accept: application/vnd.github+json` headers. Hits:
- `GET /repos/{owner}/{repo}/contents/openspec/changes` — directory listing
- For each non-archive change: `GET /repos/{owner}/{repo}/contents/openspec/changes/{change_id}/proposal.md` — H1 title extraction
- For in-impl detection: `GET /repos/{owner}/{repo}/branches/openspec/{change_id}` (404 = no branch) + `GET /repos/{owner}/{repo}/compare/main...openspec/{change_id}` with path filter

Per-source request counter enforces the budget cap; on exceedance, returns truncated result + `github_budget_exceeded` warning.

**Saved-view schema extension**

`agent-coordinator/src/schemas/kanban_viz/saved-view.json` gains an optional `hidden_repos: string[]` field under `view`. Same additive pattern as PR #211's `pr_origins` + `hidden_rows` — no schema version bump.

### SPA side

**Type extensions (`apps/kanban-viz/src/lib/coordinator-types.ts`):**

```ts
interface ProposalCard {
  // ...existing PR #211 fields...
  repo: string | null;
  change_id_namespaced: string | null;
}

interface IssueCard {
  // ...existing fields...
  repo?: string | null;   // OPTIONAL, derived client-side from labels
}
```

The contract types live in `contracts/generated/types.ts` (in-change for now, per PR #211's deferred-promotion decision). This file is a SPEC-ONLY artifact: the SPA's tsconfig has `"include": ["src"]` and cannot import from `openspec/changes/...`. The SPA's `apps/kanban-viz/src/lib/coordinator-types.ts` is a HAND-MAINTAINED runtime copy of the contract — the implementer keeps it in sync with the spec file as part of every contract change. (R1-006 fix — earlier draft said "re-exports from there", which was incompatible with the tsconfig include-path constraint stated elsewhere in this section.)

**Client-side repo derivation:**

```ts
function deriveIssueRepo(labels: readonly string[]): string | null {
  const matches = labels
    .filter(l => /^repo:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(l))
    .map(l => l.slice(5).toLowerCase());
  if (matches.length > 1) {
    console.warn(`Issue has multiple repo: labels; using first`, matches);
  }
  return matches[0] ?? null;
}
```

Called from `useBoardCards` after the `/issues/list` response is received, before clustering.

**Cluster key resolution (in `apps/kanban-viz/src/hooks/useBoardCards.ts` — `clusterBoardCards` is co-located in the hook file, NOT a standalone module):**

```ts
function getClusterKey(card: BoardCard): string | null {
  if (card.repo == null) return null;   // signals "use fallback"

  // Use the BARE change_id only. card.change_id_namespaced is ALREADY
  // <repo>/<change-id> on ProposalCard — concatenating `${card.repo}/${namespaced}`
  // would produce a doubled namespace `repo/repo/change-id` that won't match
  // sibling cards keyed off bare change_id. R1-005 fix.
  if (card.change_id == null) return null;
  return `${card.repo}/${card.change_id}`;
}

function clusterBoardCards(cards: readonly BoardCard[]): ClusterResult {
  // Group by getClusterKey; cards with null key are grouped by bare change_id
  // ONLY when no other member of that change_id group has a non-null key.
  // Mixed-null groups split.
  // ...
}
```

**New components:**

- `RepoBadge.tsx` — small chip with hash-derived color, hover tooltip, `aria-label`. Pure function from `repo: string`.
- `HiddenReposToggle.tsx` — chip group in the swimlane header listing all repos seen on the current board; click toggles hidden state, persists to saved view.

**Existing components updated:**

- `Card` (renders `IssueCard` — PR #211 file layout: there is no `IssueCardView`; `Card.tsx` is the issue renderer), `PRCardView`, `ProposalCardView` — render `<RepoBadge repo={card.repo} />` when `card.repo != null`.
- `useBoardCards` — calls `deriveIssueRepo` on every issue post-fetch; threads `hidden_repos` from saved view through to the filter step.
- `SourceSwimlanes` — renders the partial-result chip when `_warnings.length > 0`; renders `HiddenReposToggle` in the header.

### Tests

- Coordinator: pytest for `parse_sources`, `derive_local_repo`, `warm_local_sources`, the hybrid cache (local-eager + github-lazy + refresh-busts-both), the GitHub fetcher (with mocked httpx), the budget cap, the degraded-mode `_warnings` shape, the 503 fail-closed paths.
- Coordinator integration: end-to-end test booting FastAPI with a mix of local (tmp_path git repos) and github (mocked httpx) sources.
- SPA: vitest for `deriveIssueRepo` (5 scenarios from spec), `getClusterKey`, `clusterBoardCards` with mixed null/non-null fixtures, `RepoBadge` rendering, `hidden_repos` saved-view round-trip, partial-result chip.
- SPA integration: extend `e2e.integration.test.tsx` to mock multi-source `/openspec/proposals` response (including `_warnings`) + multi-repo `/issues/list` response (with `repo:` labels) and assert the integrated board renders correctly.

## Risks and Mitigations

### R1 — Lazy github cache stampede on first request

First request after coordinator boot triggers concurrent GitHub fetches across all `github:` sources. With N=5 sources, that's 5× concurrent REST clients. **Mitigation:** `asyncio.gather` with `return_exceptions=True` is the existing pattern from PR #211; the per-source mutex prevents same-source concurrent fetches. The 10s per-source timeout caps tail latency. Acceptable.

### R2 — Local-source `git remote` subprocess at boot

Boot-time `git remote get-url origin` call per local source. **Mitigation:** Subprocess with 2s timeout per source; on timeout, fall back to basename with warning. Total boot delay bounded at `2s × N_local_sources`, which is fine for N ≤ 10.

### R3 — Label convention inconsistency

Skills/agents adopting the `repo:` label convention inconsistently → some issues attributed, others not. **Mitigation:** A separate follow-up (out of scope here) updates the existing `register-feature` / `submit_work` skills to emit `repo:` labels by default. For v1, document the convention in `docs/kanban-viz/README.md` and accept the partial-attribution period.

### R4 — Cluster key resolution silently downgrades to bare change_id

A board mixing `repo: null` and `repo: "x/y"` cards with the same `change_id` could mis-cluster if the splitting rule isn't precisely tested. **Mitigation:** Spec scenarios cover the mixed-null case explicitly + vitest covers it as a regression sentinel.

### R5 — GitHub REST budget exhaustion

A repo with many changes + per-change branch probing could blow through the 50-call cap silently. **Mitigation:** The `github_budget_exceeded` warning is non-silent — the SPA's partial-result chip surfaces it. Operators can raise `OPENSPEC_SOURCES_GITHUB_CAP` if needed; the spec covers the configurable path.

### R6 — Hash-color collisions on RepoBadge

Two repos producing the same hash → same color → visually ambiguous. **Mitigation:** Use a 24-bit hash output with HSL-space color generation that constrains lightness to a readable band. Collision probability for ≤ 20 repos is negligible (birthday paradox: ~0.0001%). If it ever matters, a manual palette override could be added.

## Open Questions Carried Forward to Implementation

- **`local:` source `repo` aliasing:** Should we support `local:/path/to/repo#alias-name` syntax for cases where the operator wants a custom display name (e.g., a fork checked out at an unusual path)? Default proposal: NO for v1; keep parsing simple. Add only if requested.
- **Saved-view `hidden_repos` UX:** Shift-click on RepoBadge to hide is one option; a separate "Visible repos" filter panel in the header is another. The spec leaves the UI affordance flexible; pick one during implementation.
- **`_warnings` retention across requests:** Should a previous request's warnings persist as a sticky chip until explicitly dismissed, or only show when the LATEST refresh produced warnings? Default proposal: only latest-refresh warnings, no stickiness. Consistent with PR #211's per-row error chip.
- **Cross-repo cluster registry shape:** Deferred. When we eventually build it, the source-of-truth question (YAML in `openspec/project.md`? coordinator table? per-repo `change_id_aliases.yaml`?) needs its own discovery round.

## Residual Concerns (PLAN_ITERATE refinements)

- **Implicit-local-source convergence with `GITHUB_REPOS`:** The implicit-local-source rule assumes the coordinator's `git remote get-url origin` parses to the SAME `<owner>/<repo>` that `GITHUB_REPOS` carries (so PR↔Proposal cross-row clustering survives the namespacing). Operators who set `GITHUB_REPOS` to an UPSTREAM repo while running from a FORK checkout will see PR cards with `repo: upstream/x` but ProposalCards with `repo: fork-owner/x` — and clustering breaks. Mitigation: document the assumption in `docs/kanban-viz/README.md`; the workaround is to add the upstream as an explicit `local:` source via `OPENSPEC_SOURCES`. Not blocking; surfaced for IMPL_REVIEW.
- **Saved-view schema regex for hidden_repos:** The spec scenario for invalid `hidden_repos` entries names `"not_a_valid_entry"` — the schema regex `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` rejects it. Consistent.
- **PR #211 contract types.ts re-export `repo: string` on PRCard:** The contract types.ts uses `PRCard = PRCardBase` from PR #211, which carries `repo: string` (required, non-null). The cluster key resolution in this change treats `card.repo ?? null` — for PRCard, `??` is a no-op. Verified consistent.
- **`MultiSourceProposalListResponse` is wire-compatible with PR #211's `ProposalListResponse`:** Both have `{proposals, generated_at_iso, source, cache_age_seconds}`. New shape adds optional `_warnings` and widens `source` enum from `"live"|"cache"` to `"live"|"cache"|"mixed"`. Consumers reading `source` as a plain string see no breakage; consumers asserting against the narrowed enum would need an update. PR #211 SPA consumes `source` as informational only — not a breaker.
- **Field-shape adapter regression risk:** Mitigated via new task 3.1a (fixture-driven REST adapter test). The PR #211 CRITICAL finding pattern (`from_rest_pr` shape drift) is now headed off by an explicit `test_rest_field_shape_adapter` regression sentinel.
