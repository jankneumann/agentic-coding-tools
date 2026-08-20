# Design — Add Merge Plan Orchestration

## Context

The `merge-pull-requests` skill runs an analysis round then an interactive merge loop, both
in one long-lived context. This change introduces a durable **merge plan** that decouples
analysis from execution so each merge can run with fresh context, and so plan state can be
shared across hosts. See `proposal.md` for motivation and the selected approach (Tiered,
Approach 3).

## Decisions

### D1 — Separate plan *definition* from plan *live state*

The plan has two parts with different lifecycles:
- **Definition:** which PRs, the intended DAG, per-PR strategy, gate rules. A snapshot;
  reviewable and diffable.
- **Live state:** node status (`pending/in_progress/merged/closed/deferred/failed`),
  in-flight claims, dynamically-inserted blocker nodes, vendor-review verdicts. Hot,
  concurrently-mutated.

In the file tier, `in_progress` plus `claimed_by` is also the crash boundary. It is
atomically persisted under a same-host file lock before refresh, review dispatch, or
merge. A retry reconciles terminal GitHub state before human and sync-point gates, resumes
only the same claim, and otherwise refuses to replay an in-flight attempt. Cross-host
claim serialization remains a Phase-2 coordinator responsibility.

These are stored differently (D3). Conflating them in one flat file is what breaks
multi-host dispatch.

### D2 — The plan is a DAG, and execution re-validates downstream

Nodes are PRs; edges encode ordering dependencies from **file-overlap** (two PRs touching
the same paths) and **base-branch** relationships. Every merge into `main` can stale the
mergeability of downstream nodes (observed repeatedly: same-file dependabot PRs went
`CONFLICTING`; #227's large mirror-deletion flipped downstream PRs to `UNKNOWN`). Therefore
executing a node MUST mark downstream nodes for re-validation (recompute mergeability /
`refresh-branch`) before they are executed.

The overlap classifier intentionally measures history since PR creation, so an overlap
can remain `stale` after `refresh-branch`. Post-refresh safety therefore uses the current
CI merge-base signal, fresh passing CI, and live mergeability rather than waiting for the
historical classifier to become `fresh`.

### D3 — Tiered storage: coordinator is system-of-record; file is a projection; degrade to file

- When `CAN_QUEUE_WORK` (coordinator available): live state is authoritative in the
  coordinator, modelled as `work_queue` nodes (`task_type=pr_merge`, `blockedBy` edges,
  atomic claim via `get_work`/`complete_work`) plus `merge_queue` for the merge-into-main
  serialisation. The `merge-plan.json/.md` file is a **rendered projection** exported on
  demand.
- When no coordinator: the local `merge-plan.json` file is authoritative.
- Tier selection reuses the `merge_backend.py` detection ladder — do NOT make the
  coordinator a hard dependency (solo-dev/offline must keep working).

### D4 — Event-driven re-validation over polling (Phase 2)

With the coordinator, `event_bus` LISTEN/NOTIFY emits "`main` advanced → re-validate nodes
{X,Y}"; executors on any host react to events instead of polling. This directly replaces
the poll-and-settle loops the interactive workflow needs today. Phase 2.

### D5 — Merge-into-main stays singular; only merges serialise

Many hosts may review/prepare/refresh nodes in parallel, but the actual merge into `main`
is a sync point. It drains through the coordinator `merge_queue` (`enqueue_merge` /
`get_next_merge` / `mark_merged`), or, in the file tier, through the skill's existing
active-agents guard. Never naive-parallel push.

### D6 — Human gates are first-class; classifier is the backstop

Each node carries `auto_executable: true|false` and optional `gate` markers
(e.g. `requires_human_approval`, `admin_override_needed`). Accepting OpenSpec proposals and
admin-merging past a failing gate are human decisions — the orchestrator stops and asks.
The existing auto-mode classifier remains the independent backstop that refuses merging
past a failing security check even if a plan says `auto_executable`.
The semantic contract rejects contradictory gate/auto declarations. OpenSpec nodes are
always non-auto-executable, always carry `proposal_acceptance`, and are never released by
the executor's generic approval flag.

### D7 — Living plan: execution may amend the definition

An execution step that discovers a blocker (the `joserfc` CVE case) MAY insert a new
prerequisite node and add `blockedBy` edges from the affected nodes, then persist the
amendment (to coordinator or file per tier). Amendments are append-oriented and carry a
reason; they never silently drop existing nodes.

### D8 — Comment-addressing is a delegation seam, not automated here

Execution that encounters unresolved review comments records them on the node and (in
interactive/manual use) hands off to `iterate-on-implementation`/`quick-task`. This change
defines the seam and the node fields; it does NOT dispatch code-writing sub-agents.
Rationale: background `Task` agents run in the main repo dir, not a worktree — safe
automation needs worktree-isolated dispatch, a separate change.

### D9 — Executors use canonical `skills/...` paths

Plan-driven execution resolves the repository root first and invokes helper scripts via
canonical `skills/merge-pull-requests/...` paths, never an `.agents/skills`,
`.claude/skills`, or other runtime mirror — mirrors are generated and can vanish mid-run.

### D10 — Auth scoping is a Phase-2 requirement, not an afterthought

Cloud-SDK executors reach plan state over the HTTP API. A known permission gap returns 403
for some coordinator ops with the local-profile API key. Phase-2 plan endpoints MUST define
the required scope explicitly rather than discovering the gap at runtime.

## Phasing

- **Phase 1 (this change implements):** file-tier `merge-plan.json` + rendered `.md`
  emitted by the analysis round; `--execute --pr <n>` consumption; downstream
  re-validation (D2); living-plan amendment against the file (D7); gate handling (D6);
  canonical paths (D9). No coordinator needed.
- **Phase 2 (specified, deferred):** coordinator system-of-record (D3), event-driven
  re-validation (D4), merge-queue serialisation across hosts (D5), auth scoping (D10).

## Risks / Trade-offs

- Two storage tiers to keep coherent — mitigated by making the file a pure projection of
  the same schema the coordinator serves.
- JSON and Markdown cannot be renamed atomically as a pair — mitigated by preparing both,
  publishing JSON last as the commit marker, and repairing Markdown from authoritative
  JSON on load after an interrupted write.
- The DAG's file-overlap edges are heuristic (path intersection) and may over- or
  under-connect; execution's downstream re-validation (D2) is the safety net that catches
  a missed edge before a bad merge.
- The plan can drift from GitHub reality between analysis and execution — `--execute`
  always re-checks live PR/CI state before merging rather than trusting the snapshot.
