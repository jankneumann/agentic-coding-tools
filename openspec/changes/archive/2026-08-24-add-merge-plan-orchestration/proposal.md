# Add Merge Plan Orchestration

## Why

The `merge-pull-requests` skill's analysis round (`discover_prs`, `check_staleness`,
`analyze_comments`, `vendor_review`) produces **ephemeral** output — it is re-derived
from scratch every session. In a real multi-PR triage this month, the analysis state
had to be reconstructed **by hand** into a memory file plus a task list in order to
survive a context clear. There is no durable plan artifact and no plan→execute split,
which causes three concrete problems:

1. **No fresh-context-per-merge.** A long triage session accumulates unrelated context
   (this session spent thousands of tokens investigating a `joserfc` CVE before merging
   anything). Each PR merge would reason more cleanly, cheaply, and reproducibly from a
   fresh context seeded only by the plan.
2. **No safe multi-host dispatch.** Work is increasingly dispatched from several places
   at once — locally, from other machines on the LAN, and into the cloud via SDKs. A
   flat JSON on one machine's disk has no concurrency control, no change notification,
   and git-committing every mutation serialises through push/pull and pollutes history.
3. **The plan must be dynamic, not static.** During the motivating session a HIGH-severity
   `joserfc` auth-bypass CVE was discovered **mid-execution** and re-ordered the entire
   cohort (fix the CVE first → every blocked PR then cascades green). A pre-baked static
   plan cannot represent a blocker discovered during execution.

The skill already ships the *execution* substrate for this — `merge_backend.py`
(Coordinator Train / GitHub queue / Direct), `merge_watcher.py`, `vendor_review.py`,
`check_staleness.py`, `post_merge_pipeline.py` — plus the coordinator's `work_queue`,
`merge_queue` (`enqueue_merge`/`get_next_merge`/`compose_train`/`mark_merged`), and
`event_bus` (LISTEN/NOTIFY). What is missing is the **connective tissue**: a durable,
living plan and the plan→execute split. This is an extension, not a rewrite.

## What Changes

- **New durable merge-plan artifact.** A machine-readable `merge-plan.json` (with a
  rendered `merge-plan.md` projection for humans) emitted by the analysis round,
  capturing per PR: classification, staleness, CI/gate state, unresolved-comment count,
  **a merge-order DAG** (edges = file-overlap + base-branch dependencies), strategy
  (rebase/squash), an `auto_executable` flag plus `gate` markers, and a mutable
  `outcome` slot (`pending → merged | closed | deferred`) with the vendor-review verdict.
- **Plan-driven single-PR execution mode.** `merge-pull-requests --execute <plan> --pr <n>`
  loads the plan, refreshes the branch, runs vendor review, merges (respecting gates),
  writes the outcome back, and **re-validates downstream plan entries**. This is the
  fresh-context-per-merge primitive, runnable manually after `/clear`. Works solo, no
  coordinator required.
- **Living-plan amendment.** An execution step MAY amend the plan by inserting a
  discovered prerequisite node and re-drawing affected DAG edges (the `joserfc` case).
- **Tiered plan storage (design + Phase-2 spec).** The coordinator is the system of
  record for live plan state (modelled as an extension of `work_queue` + `merge_queue`),
  with the JSON/MD file as an exported projection; degrades to a local plan file when no
  coordinator is available. Event-driven re-validation over the existing `event_bus`
  replaces polling. **Phase 2** — specified here, implemented in a follow-on.
- **Explicit human gates.** PRs are marked `auto_executable: true|false`. Accepting
  OpenSpec proposals and admin-merging past a failing gate remain human decisions; the
  orchestrator stops at gated PRs and asks. The existing auto-mode classifier remains the
  backstop against merging past a failing security check.

## Out of Scope

- **Automated comment-addressing.** Sub-agents that check out a PR branch, write code to
  resolve review comments, and push are **deferred**. This change specifies the
  *delegation seam* (execution hands off to `iterate-on-implementation`/`quick-task`) but
  does not automate code-writing. Rationale: comment-addressing is a mini
  `implement-feature` and carries the most risk; and background `Task` agents run in the
  main repo dir, not a worktree, so safe automation needs worktree-isolated dispatch that
  deserves its own change.
- **Replacing the interactive workflow.** The existing interactive triage remains; the
  plan artifact augments it.
- **New merge backends.** Reuses `merge_backend.py`'s existing backend selection ladder.

## Approaches Considered

### Approach 1 — File-only plan (no coordinator)

The plan is a `merge-plan.json` on local disk; all state (definition + live) lives in the
file. Execution reads/writes the file directly.

- **Pros:** Simplest; zero new infra; trivially diffable/reviewable; works fully offline.
- **Cons:** No concurrency control for multi-host dispatch (two executors racing on the
  file corrupt state); no change notification (executors poll); git-committing live-state
  mutations pollutes history and serialises through push/pull. Fails the multi-host
  requirement.
- **Effort:** S

### Approach 2 — Coordinator-only plan (DB is the only home)

Plan definition *and* live state live exclusively in the coordinator DB; there is no file
artifact. Humans query the DB (or a rendered view) to inspect the plan.

- **Pros:** Single source of truth; transactional concurrent updates; event notifications;
  natural multi-host and cloud-SDK access via the existing HTTP + MCP transports.
- **Cons:** Makes the coordinator a **hard dependency** — breaks the solo-dev/offline path
  the repo explicitly supports; loses the diffable/reviewable snapshot (you can't attach a
  DB row to a PR); larger up-front migration before any value ships.
- **Effort:** L

### Approach 3 — Tiered: coordinator system-of-record + file projection, degrade to file (Recommended)

Separate **plan definition** (which PRs, intended DAG, strategies, gate rules — a
reviewable snapshot) from **plan live state** (nodes merged/failed/blocked, in-flight
claims, inserted blockers — hot mutable shared state). The coordinator is the system of
record for live state when available (`CAN_QUEUE_WORK`), modelled as an extension of
`work_queue` (`task_type=pr_merge` nodes with `blockedBy` edges + atomic claim) and
`merge_queue` (serialises the singular merge-into-main sync point), with `event_bus`
LISTEN/NOTIFY driving re-validation. The JSON/MD file is an **exported projection** for
humans/review. When no coordinator is present, the local plan file is authoritative.
Storage tier is chosen exactly like the existing `merge_backend.py` degradation ladder.

- **Pros:** Ships value solo first (file tier); earns the coordinator's concurrency +
  events precisely when multi-host dispatch demands it; keeps a diffable snapshot;
  reuses three existing coordinator subsystems rather than inventing one; mirrors the
  skill's established "best-available, degrade-gracefully" pattern.
- **Cons:** Two storage tiers to keep coherent (projection ↔ system-of-record); auth
  scoping for cloud-SDK access is a real requirement (a known permission gap returns 403
  for some coordinator ops with the local-profile key); the coordinator path is the
  larger Phase-2 lift.
- **Effort:** M (Phase 1) + L (Phase 2)

### Selected Approach

**Approach 3 (Tiered).** It is the only approach that satisfies both the solo-dev/offline
constraint *and* the multi-host dispatch goal, and it reuses existing coordinator
subsystems instead of building a parallel one. This change **specifies the full tiered
architecture** (proposal + design) but **implements Phase 1 only** (file-tier artifact +
`--execute --pr <n>` + downstream re-validation, which works with no coordinator); Phase 2
(coordinator system-of-record, event-driven re-validation, cross-host dispatch, auth
scoping) is specified as deferred requirements and implemented in a follow-on change.
Automated comment-addressing is out of scope (delegation seam only), per the scope
decision recorded in `design.md`.
