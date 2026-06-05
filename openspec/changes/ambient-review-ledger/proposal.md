# Proposal: Ambient Continuous Review with a Self-Verifying Finding Ledger

**Change ID**: ambient-review-ledger
**Status**: Draft
**Created**: 2026-06-03
**Tier**: coordinated

## Why

Our review stack is **gated and ceremonial**: multi-vendor consensus runs at the
plan gate (`parallel-review-plan`), the implementation gate
(`parallel-review-implementation`), and the PR gate (`merge-pull-requests`
Step 9). Between those gates an implementing agent can produce dozens of commits
with no review signal at all, so defects compound silently until a gate fires —
at which point the consensus reviewers face a large, cold diff.

[roborev](https://www.roborev.io) demonstrates the complementary model: a
**continuous, commit-granular sensor**. A `post-commit` hook queues every commit
for fast asynchronous review, findings accumulate in a persistent ledger, and a
`compact` pass re-verifies open findings against current code so the ledger
self-cleans as the work evolves.

We want the continuous sensor to **feed** our gates, not replace them. Gate-time
consensus should start from an already-curated, self-verified ledger instead of
a cold diff. This change adapts roborev's continuous-review concepts onto our
existing coordinator + skills infrastructure, **reusing** the
`review-findings` / `consensus-report` schemas and the
`consensus_synthesizer` / `convergence_loop` / `checkpoint_findings` machinery
rather than inventing parallel ones.

This change is explicitly scoped to **complement** the existing gate-time
multi-vendor consensus review — it adds a fast single-vendor ambient layer
*beneath* the gates, never weakening the consensus requirement *at* the gates.

## What Changes

Five capabilities, delivered as phases of a single change. Phase 0 de-risks the
overlap with the in-progress `harness-engineering-features` change (see Risks).

- **Phase 0 — Extract `refine-core` (shared backbone).** Extract the iterate /
  synthesize / fix / validate primitives currently embedded in
  `skills/autopilot/scripts/convergence_loop.py` into a reusable
  `skills/parallel-infrastructure/scripts/refine_core.py` module. Both this
  change (Phase 3 standalone refine) and `harness-engineering-features`
  Feature 1 consume `refine-core` instead of editing `convergence_loop.py`
  directly, so neither change owns the other's file edits.

- **Phase 1 — Ambient continuous review (item #1).** Add a `post-commit` git
  hook (alongside the existing `.githooks/pre-commit` and `post-merge`) that, by
  default, queues a fast **single-vendor** review of each commit during active
  implementation. Results are written using the existing
  `openspec/schemas/review-findings.schema.json` and surfaced via the
  coordinator work-queue. A documented kill-switch
  (`REVIEW_AMBIENT=0` / config flag) disables it for a repo or session.

- **Phase 2 — Durable finding ledger + `compact` re-verification (item #2).**
  Promote findings from ephemeral per-gate JSON snapshots to a **local-first
  ledger** (`.review-ledger/`) with an `open → addressed → retired` lifecycle,
  synced to the coordinator (`memory`/`audit`) when reachable. A `compact` pass
  re-checks open findings against current `HEAD`, retires stale/fixed ones, and
  consolidates duplicates by reusing `consensus_synthesizer.py` matching logic.

- **Phase 3 — Standalone refine loop (item #3).** Expose a low-ceremony
  "fix until clean" entry point over `refine-core` that operates on any branch
  or commit range *without* the full autopilot/OpenSpec pipeline — the
  equivalent of `roborev refine`. Pairs with `quick-task` and `/code-review`.

- **Phase 4 — Findings → issue tracker (item #4).** Auto-file confirmed/blocking
  ledger findings as GitHub issues via the existing GitHub MCP tools, and
  auto-close them when Phase 2's `compact` re-verification marks them retired.

- **Phase 5 — Review-ledger view in `apps/kanban-viz` (item #5).** Add a
  findings-ledger swimlane to the existing SSE-fed Kanban board so ledger state
  (open / addressed / retired, by severity and vendor) is observable — the
  roborev TUI equivalent on our existing observability surface.

### Non-goals

- Replacing or weakening gate-time multi-vendor consensus review.
- Multi-vendor consensus *at ambient time* (ambient review is deliberately
  single-vendor and fast; consensus remains a gate concern).
- A new TUI binary — observability rides on the existing `kanban-viz` app.
- Reviewing untrusted third-party code (same trusted-codebase assumption as the
  rest of the stack; ambient review agents run read-only).

## Approaches Considered

### Approach A — Hook-driven local-first ledger that feeds the gates *(Recommended)*

A `post-commit` git hook enqueues a fast single-vendor review; findings land in a
local-first `.review-ledger/` synced to the coordinator; a `compact` pass
self-verifies the ledger; gate-time skills read the curated ledger as a warm
starting point. The refine loop and consensus dedup are shared via `refine-core`
and `consensus_synthesizer`.

- **Pros**
  - Matches roborev's proven "catch it before it compounds" property — review is
    automatic and push-based, not something an agent must remember to run.
  - Local-first ledger keeps working when the coordinator is unreachable
    (offline CLI, degraded network), syncing opportunistically.
  - Maximises reuse: review-findings/consensus schemas,
    `consensus_synthesizer`, `checkpoint_findings`, `convergence_loop`
    (via `refine-core`) are all existing assets.
  - Cleanly complements gates — the sensor feeds the gate, no behavior at the
    gate is weakened.
- **Cons**
  - On-by-default ambient review costs an LLM call per commit (mitigated by
    single-vendor fast tier + kill-switch).
  - Local + coordinator dual store adds a sync/reconciliation path.
  - A new git hook is one more piece of local setup to install and document.
- **Effort**: L

### Approach B — Coordinator-daemon-driven server-side review (no git hook)

A coordinator background worker watches the work-queue / commit stream and
schedules reviews server-side; the ledger lives only in the coordinator DB.

- **Pros**
  - No per-developer git-hook installation; centralized control and metrics.
  - Single source of truth for the ledger (no local/remote reconciliation).
- **Cons**
  - Hard coordinator dependency — contradicts the chosen *local-first* posture
    and breaks offline/degraded-network CLI use.
  - Server can't see commits until they're pushed/registered, losing the
    "review the instant it lands locally" property that makes ambient review
    valuable.
  - Larger coordinator surface to build, operate, and secure.
- **Effort**: L

### Approach C — Skill-orchestrated pull model (extend `/code-review` + `/loop`)

No new hook or daemon: drive ambient review by running the existing
`/code-review` skill on a manual or `/loop` interval; persist findings as
artifact files.

- **Pros**
  - Smallest new infrastructure; reuses `/code-review` and `/loop` as-is.
  - Zero per-commit cost unless the operator opts to run it.
- **Cons**
  - Loses the *ambient/automatic* property — it is pull, not push; relies on the
    operator/agent remembering to trigger it, which is exactly the failure mode
    roborev's hook exists to remove.
  - No natural commit-granular trigger; drift can still compound between manual
    runs.
  - Ledger lifecycle (`compact`, retire) has no clear owner without a persistent
    store.
- **Effort**: M

### Selected Approach

**Approach A — Hook-driven local-first ledger that feeds the gates.** Confirmed
at Gate 1 with no modifications. This selection is consistent with the four
discovery decisions: one phased change, Phase 0 `refine-core` extraction to
de-conflict with `harness-engineering-features`, on-by-default ambient review
with a kill-switch, and a local-first ledger that syncs to the coordinator.

### Recommendation

**Approach A.** It is the only option that preserves roborev's defining
property — automatic, commit-granular, push-based review — while honoring the
operator's chosen *local-first* ledger posture and *on-by-default* ambient mode.
Approach B's hard coordinator dependency directly contradicts the local-first
decision; Approach C sacrifices the ambient/automatic property that is the whole
point of the change. Approach A also maximises reuse of existing schemas and
synthesis/convergence machinery, keeping the net-new surface focused on the
hook, the ledger lifecycle, and the `compact` re-verification pass.

## Risks

- **Overlap with `harness-engineering-features` Feature 1** (both touch
  `convergence_loop.py` / `consensus_synthesizer.py`). *Mitigation*: Phase 0
  extracts `refine-core`; both changes consume it instead of editing the
  convergence loop directly. Phase 0 must land (and ideally merge) before
  Phase 3, and should be coordinated with that change's owner.
- **Cost/noise from on-by-default ambient review.** *Mitigation*: single-vendor
  fast tier (`economy`/`standard` archetype), documented kill-switch, and the
  `compact` pass that suppresses duplicate/stale findings.
- **Ledger sync divergence** between local and coordinator copies.
  *Mitigation*: local file is the source of truth; coordinator sync is
  best-effort and idempotent on a stable finding id (same pattern as
  `checkpoint_findings`).
- **Prompt-injection via reviewed diffs.** *Mitigation*: ambient review agents
  run read-only (no fix authority); the trusted-codebase assumption is documented
  as a non-goal boundary.

## Impact

- **New**: `skills/parallel-infrastructure/scripts/refine_core.py`,
  `.githooks/post-commit`, a review-ledger library + schema, a `compact`
  re-verification script, a standalone refine entry point, a GitHub-issue sync
  script, a `kanban-viz` ledger swimlane.
- **Modified**: `skills/autopilot/scripts/convergence_loop.py` (delegates to
  `refine-core`), `.githooks` installer, `apps/kanban-viz` (new swimlane + SSE
  event), gate skills read the ledger as warm context (additive).
- **Reused**: `review-findings.schema.json`, `consensus-report.schema.json`,
  `consensus_synthesizer.py`, `checkpoint_findings.py`, coordinator
  `memory`/`audit`/`work-queue` services, GitHub MCP tools.
