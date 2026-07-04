# Repository Improvement Roadmap: Durable Loops, Dynamic Dispatch, and Cloud/Local Task Routing

**Roadmap ID**: repo-improvement
**Status**: Draft
**Created**: 2026-07-04

## Executive Summary

This repository has built an unusually complete software factory: a Postgres-backed coordinator with ~70 MCP tools and 81 HTTP routes, a 14-phase autopilot state machine with multi-vendor review convergence, a roadmap orchestrator with checkpointed learning feedback, a four-source episodic-memory pipeline, and a CI-gated decision index. The *write* side of the system — state, checkpoints, audit, memory, specs — is strong and largely automated.

The gap is on the *dispatch and continuation* side. Three structural weaknesses keep the automatic coding loops from running unattended:

1. **Routing is reactive, not proactive.** No component ever decides *where a task should run*. Vendor selection is manual or "first available" (`skills/quick-task/scripts/quick_task.py:100-108`); cloud-vs-local detection describes where the current agent *already* runs, never where work *should* go (`skills/shared/environment_profile.py`); the roadmap policy engine only reacts to rate limits, with cost/wait estimators that are documented stubs (`skills/autopilot-roadmap/scripts/policy.py:206-241`) and a hardcoded vendor list (`skills/autopilot-roadmap/scripts/orchestrator.py:317-319`). Worse, when the policy engine decides to switch vendors, the orchestrator only *logs* the decision — nothing executes it (`orchestrator.py:264-272`).

2. **Loops are single-session and mortal.** `autopilot-roadmap` is a `while True` loop inside one agent session (`orchestrator.py:128-187`). When the session ends — context exhaustion, usage limit, machine sleep — the loop dies. Checkpoints make resume *possible*, but nothing makes resume *happen*. Every human gate (proposal approval, escalation, merge) parks the entire loop instead of parking one item. The harness primitives that solve this — scheduled triggers, self-wakeups, background agents, fresh-session-per-fire dispatch, PR-event subscriptions — exist today and are used nowhere in the repo.

3. **The feedback loops are wired but hand-cranked.** Dispatch outcomes, convergence metrics, and capability gaps all land in episodic memory, but no scheduler runs `collect-transcripts`/`improve-harness`, nothing feeds outcomes back into routing decisions, and async vendor results are harvested by regex-scraping CLI stdout (`agent-coordinator/agents.yaml:241-243`, `review_dispatcher.py:461-469`) — the most fragile link in the whole chain.

This roadmap fixes those three weaknesses in dependency order, plus the hygiene debt that would otherwise undermine them. It is structured so `/plan-roadmap` can decompose it directly: each item has deliverables, acceptance outcomes, effort, and dependency edges.

---

## Part 1 — Architecture Assessment

### 1.1 Strengths worth preserving

| Strength | Evidence |
|---|---|
| **Coordinator as single source of coordination truth** — locks, queue, memory, audit, approvals, merge train all behind one service layer reachable via MCP *and* HTTP, "coordination happens at the database level, not the transport level" | `agent-coordinator/src/`, `skills/setup-coordinator/SKILL.md:20` |
| **Test culture in the coordinator** — 114 test files / ~1,769 tests incl. property-based and invariant suites; test LOC exceeds source LOC | `agent-coordinator/tests/` |
| **Durable convergence loop** — per-round review checkpoints written *before* synthesis, quorum rules, stall detection, escalation on vendor disagreement | `skills/autopilot/scripts/convergence_loop.py:387-445, 578-610` |
| **The archetype system as a routing seam** — phase → archetype → tier → per-vendor model, resolved server-side, tunable in YAML without code changes | `agent-coordinator/archetypes.yaml`, `POST /archetypes/resolve_for_phase` |
| **Checkpoint-everywhere state** — `loop-state.json` (schema-versioned, forward-migrating), roadmap `checkpoint.json`, `.review-cache/`, `.dispatch-state.json` with sha256-checksummed replay idempotency | `autopilot.py:56-137`, `phase_agent.py:1007-1130` |
| **D4 memory tag schema as an emitter/consumer contract** — four signal sources with documented bias profiles, one consumer | `docs/guides/memory-conventions.md`, `2026-06-07-harness-engineering-features/design.md` |
| **CI-gated generated artifacts (partially)** — the decision index fails CI on drift; OpenSpec validated `--strict --all` | `.github/workflows/ci.yml:80-125` |
| **Harness-agnosticism by design** — same SKILL.md drives Claude Code, Codex, Gemini; `AGENTS.md → CLAUDE.md` symlink | `README.md:7`, `skills/install.sh` |

### 1.2 Weakness themes

**W1 — No proactive router (the core gap).**
The system knows *how* to talk to six execution targets (`claude|codex|gemini` × `local|remote`, `agents.yaml:44-266`) but has no component that maps a task's profile to a target. Consequences:
- Worker vendor = whichever harness happens to be running (`implement-feature/SKILL.md:173-203`).
- Cloud execution is never *chosen*; it happens only if the operator started a cloud session.
- `preferred_vendor`/`cost_ceiling_usd` ship commented out in the roadmap template; default policy is `wait`, so cross-vendor failover is off in practice (`openspec/schemas/roadmap/templates/roadmap.yaml:9-13`).
- The archetype resolver picks a *model tier* but not a *location* or *vendor* — one axis of a three-axis decision.

**W2 — Loop mortality and blocking gates.**
- `autopilot-roadmap` has no global iteration cap (contrast autopilot's `max_global_iterations=50`) and no continuation mechanism beyond "a human re-invokes the skill."
- ESCALATE pauses the inner loop in place (`autopilot.py:511-514`); a single blocked item stalls attention on the whole roadmap even though `_get_ready_items` could keep other items flowing.
- Async vendor waits (Codex cloud, Jules) are handled by blocking poll loops inside the session (`review_dispatcher.py:373-580`) — burning context and wall-clock on `sleep`-style polling that the harness could do for free.

**W3 — Brittle dispatch/result mechanics.**
- Task IDs and completion states are regex-scraped from vendor CLI stdout (`task_id_pattern`, `success_pattern: "completed|finished|merged|done"` — `agents.yaml:241-243`). Any CLI output change silently breaks harvesting.
- SDK fallback is review-only (`review_dispatcher.py:606-614`) — no API-based implementation path when a CLI is missing.
- PR-based results (Jules, Codex cloud) are collected by a *manually invoked* `/merge-pull-requests` sweep, not by event subscription.
- Cloud session end leaks locks for up to the 120-min TTL because the HTTP API lacks "list locks by agent" (`docs/cloud-session-hooks.md:38-45`).

**W4 — Learning loop is built but not turned on.**
- No cron/CI/trigger runs `collect-transcripts` or `improve-harness`; capability-gap signal accumulates unread.
- `replanner.replan()` is regex priority-nudging, not re-planning; `replan_required` is a documented dead status (`autopilot-roadmap/SKILL.md:155-164`).
- Dispatch outcomes (which vendor succeeded at which phase, at what cost, in how many convergence rounds) are recorded in memory/audit but never consulted by any routing decision.
- Architecture artifacts are stale past their own warning threshold (`docs/architecture-analysis/`, generated 2026-05-30 vs HEAD 2026-06-25) while skills are told to trust them for parallel-zone safety.

**W5 — Hygiene debt that erodes trust in automation.**
- The committed skill mirrors (`.claude/skills/`, `.agents/skills/`) have **no CI drift gate** against canonical `skills/` — the single biggest drift risk in a repo whose product *is* the skills.
- `.githooks/` exists but `core.hooksPath` is not wired by any setup path — pre-commit guarantees are opt-in and probably inactive for most clones.
- Version drift: root `VERSION`=0.2.0 vs `agent-coordinator`/`gen-eval`/`kanban-viz` at 0.1.0; no git tags, no release workflow.
- Non-blocking CI: gen-eval `mypy --strict` and the TLA+ job are `continue-on-error`; kanban-viz tests appear in no CI job; `tests/test_architecture/`, `scripts/tests/`, `test_opsx_e2e.sh` are orphaned from automation.
- Monoliths: `coordination_api.py` (3,329 LOC) and `coordination_mcp.py` (3,199 LOC).
- Docs-vs-reality drift: coordinator CLAUDE.md status checklist, README tool/migration counts, `pyproject` 0.1.0 vs `/health` 0.2.0, retired-but-present `verification_gateway/`, divergent `formal/` vs `agent-coordinator/formal/`.
- Memory tag schema duplicated in 4 places; skill tree in 3.

### 1.3 New harness primitives this roadmap exploits

The current dispatch layer predates a generation of harness features. Mapping them to the repo's needs:

| Harness primitive | What it replaces / enables here |
|---|---|
| **Background subagents** (`Agent` tool, async by default, completion notifications) | In-session blocking waits on vendor polls; sequential phase execution that could overlap |
| **`Workflow` tool** (deterministic `pipeline()`/`parallel()` fan-out, schema-validated `agent()` outputs, per-call `model`/`effort`/`isolation`, resume-from-run-id) | The review-convergence fan-out (`ReviewOrchestrator` subprocess dispatch) for same-vendor reviewers; structured findings without stdout JSON-parsing |
| **`/loop` + `ScheduleWakeup`** (self-paced recurring re-entry with dynamic delays) | Poll loops for async cloud vendors — sleep exactly as long as the vendor's typical turnaround, resume from checkpoint on wake |
| **Scheduled triggers / cron** (`create_trigger`, `send_later`, run-once and recurring; can fire into this session, a named session, or a **fresh session per fire**) | Loop mortality: nightly roadmap ticks, hourly PR babysitting, resume-after-limit-reset (the `wait_if_budget_exceeded` policy can *schedule its own resume*) |
| **Fresh cloud sessions per dispatch** (`create_new_session_on_fire`, isolated containers, setup scripts) | A true "cloud lane": each roadmap item or work package as an independent cloud session with its own container — no worktree juggling, results as PRs |
| **PR activity subscriptions** (`subscribe_pr_activity`: CI events, review comments delivered as webhooks) | The manual `/merge-pull-requests` sweep for async-vendor PR collection; autopilot's post-SUBMIT_PR blindness |
| **Structured output schemas on subagents** | `review-findings.schema.json` enforcement at the tool-call layer instead of parse-and-pray |

**Design constraint — keep harness-agnosticism.** These primitives are Claude-Code-specific. They must land behind the same adapter seam that already isolates vendor CLIs (`CliVendorAdapter`): a *dispatch-capability* layer where the Claude adapter uses native background agents/workflows/triggers, and Codex/Gemini adapters keep subprocess+poll. The SKILL.md contract stays vendor-neutral; only adapters know the primitives. This mirrors the repo's existing pattern (transport-agnostic bridge, tier degradation) and is a hard requirement, not a preference.

---

## Part 2 — Roadmap

Five phases, sixteen items. Effort: S ≈ ≤1 change, M ≈ 1 substantial change, L ≈ 2–3 changes or a mini-roadmap.

### Phase 0 — Trust foundations

> Everything later assumes the automation can be trusted. These are cheap, independent, and should go first (or in parallel with Phase 1).

#### RI-1: Gate the drift — mirrors, hooks, orphaned tests, blocking CI (Effort: M, Depends: —)

**What**: Make the existing quality machinery actually enforce.
- Add `install.sh --check` (dry-run rsync `--itemize-changes`, exit non-zero on diff) and a CI job failing when `.claude/skills/` / `.agents/skills/` drift from `skills/` — same pattern as `validate-decision-index`.
- Wire `core.hooksPath=.githooks` into every bootstrap path (`Makefile` target, `skills/install.sh`, `session-bootstrap/setup-cloud.sh`) and delete `.githooks/pre-commit.old` (fold its home-path check into the active hook).
- Adopt the orphans: run `tests/test_architecture/` and `scripts/tests/` in CI or delete them; wire `test_opsx_e2e.sh` or move it under an existing suite.
- Promote `continue-on-error` steps: make gen-eval `mypy --strict` blocking (fix or baseline current errors); keep TLA+ advisory but emit a visible badge. Add a Node job for `apps/kanban-viz` (lint + vitest).

**Acceptance**: editing a mirror file (or forgetting to sync) fails CI; a fresh clone gets active git hooks without manual steps; no test file in the repo is outside CI.

#### RI-2: One version, one truth (Effort: S, Depends: —)

**What**: Reconcile versioning and stale docs.
- Single-source the version: root `VERSION` feeds `agent-coordinator`, `packages/gen-eval`, `skills`, `apps/kanban-viz` (hatch/vite can read it at build time); align the `/health` report.
- Tag `v0.2.0`; add a minimal tag-triggered release workflow (changelog check + tag + GitHub release) leaning on the existing `changelog-version` skill.
- Fix documented drift: coordinator `CLAUDE.md` status checklist, README tool/migration counts, retired `verification_gateway/` mention-or-remove, consolidate `formal/` vs `agent-coordinator/formal/` (pick one home; delete or clearly archive the divergent copy).
- Single-source the D4 memory tag schema: one canonical file (e.g. `docs/guides/memory-conventions.md` or a small JSON schema) that `memory.py`, `session-log`, and `improve-harness` docs reference instead of restating.

**Acceptance**: `git tag` non-empty; one grep finds exactly one authoritative statement of the tag schema; component manifests agree with `VERSION`.

### Phase 1 — The routing engine: proactive dispatch to cloud and local agents

> This is the heart of the roadmap. Order matters: structured results (RI-3) and a live registry (RI-4) are the inputs a router (RI-5) needs; execution (RI-6) is what makes its decisions real.

#### RI-3: Structured vendor result channel (Effort: M, Depends: —)

**What**: Eliminate regex-scraping as the result-collection mechanism.
- Switch every CLI adapter to its vendor's structured output mode (`claude --print --output-format json`, Codex/Gemini JSON flags) and parse typed envelopes; keep the regex path only as a tagged legacy fallback per vendor with a deprecation date.
- For async dispatches, replace "poll stdout for `completed|finished|merged|done`" with a completion ledger in the coordinator: the dispatching side records `submit_work`, the harvesting side is either (a) vendor CLI status in JSON, or (b) for PR-producing vendors, PR state via the GitHub API keyed by branch naming convention — both writing `complete_work` so *the work queue is the single source of dispatch state*.
- Fix the cloud lock-leak: add `GET /locks?agent_id=` + bulk release to the HTTP API so `deregister_agent.py` can release locks at session end instead of waiting out the 120-min TTL.
- Extend `SdkVendorAdapter` beyond review-only where feasible, or explicitly document per-vendor which modes have no CLI-less fallback.

**Acceptance**: no `task_id_pattern`/`success_pattern` regex remains on the primary path for any vendor; a vendor CLI output-format change degrades to a *loud* structured error, not silent hang; killed cloud sessions release their locks.

#### RI-4: Live vendor capability & cost registry (Effort: M, Depends: —)

**What**: Turn `agents.yaml` from static config into a registry backed by live state.
- Add a coordinator `vendor_registry` service: per agent (`claude-local`, `codex-remote`, …) hold *static* capabilities (modes, isolation, max context, supports-async) from `agents.yaml` plus *dynamic* state — availability (fed by `vendor-status` probes on a heartbeat), current rate-limit/usage windows (recorded whenever a 429/limit error is seen, with known reset time), and a real cost table (per-model $/Mtok, maintained as versioned data — replacing the `policy.py:221-241` stub tiers).
- Expose `GET /vendors` + `GET /vendors/{id}/availability`; teach `coordination_bridge.py` the same.
- Delete the hardcoded `["claude", "codex", "gemini"]` in `orchestrator.py:317-319` — available vendors come from the registry, filtered by required capability.

**Acceptance**: `evaluate_policy` receives live availability and real cost deltas; taking a vendor offline (or hitting its limit) is visible in the registry within one probe interval and changes routing output.

#### RI-5: The task router — vendor × location × model (Effort: L, Depends: RI-4)

**What**: Extend the archetype resolver into a full routing decision. New endpoint `POST /route/task` (and bridge function), superset of `/archetypes/resolve_for_phase`:
- **Input — a task routing profile**: phase/archetype signals (already defined in `archetypes.yaml` `phase_mapping`), plus routing-specific signals: expected duration, scope size (`write_allow` breadth, LOC estimate), interactivity (does it need human gates mid-task?), secret/credential needs (cloud containers may lack them), parallelism (is it one of N independent packages?), repo-access shape (single repo vs cross-repo), and the roadmap `Policy` (preferred vendor, cost ceiling).
- **Output**: `{vendor, location: local|cloud, model, isolation, dispatch_mode, rationale}` — three axes plus an audit-ready rationale string.
- **v1 policy is deterministic rules**, versioned in YAML next to `archetypes.yaml` (e.g. `routing.yaml`): long-running + non-interactive + independent → cloud; needs local secrets/Docker validation → local; review fan-out → all available vendors minus worker (existing diversity policy folds in as one rule); implementer for tiny scoped package → economy tier local. Rules are unit-testable table lookups — no ML, no magic.
- Record every routing decision + eventual outcome to the audit log under a `routing:` event type (consumed later by RI-13).
- Honor the existing degradation ladder: coordinator down → local static fallback table shipped with the skill (same shape), so routing never blocks work.

**Why here and not in each skill**: the coordinator already owns per-phase model resolution, vendor identity, and the audit trail; putting location+vendor in the same resolver keeps one decision point, one config file, one test surface — and every harness (Claude/Codex/Gemini) gets the same router through the bridge.

**Acceptance**: given a synthetic task profile, `POST /route/task` returns a deterministic, explainable decision; changing `routing.yaml` changes decisions with no code edits; every autopilot phase dispatch logs a routing record with rationale.

#### RI-6: Make the orchestrator obey the router (Effort: M, Depends: RI-3, RI-5)

**What**: Close the decide-but-don't-act gaps in `autopilot-roadmap` and `autopilot`.
- `orchestrator.py`: call `route/task` before each `dispatch_fn`; pass the routing decision *into* the dispatch context as a contract (vendor, location, model), not a log line. On `switch` decisions, re-route and re-dispatch — verify the next dispatch actually used the alternate vendor (assert against the dispatch record from RI-3's ledger).
- Add the missing global safety cap to the roadmap loop (mirror autopilot's `max_global_iterations`), plus a no-progress detector (K consecutive iterations without a state transition → checkpoint + escalate).
- Un-stub `_estimate_cost_delta`/`_estimate_wait_seconds` against the RI-4 registry.
- Fix the silent no-op in `apply_phase_outcome` when the state file is missing (`phase_agent.py:1031-1038`) — that should be an error, not a log line.

**Acceptance**: an induced rate-limit on the preferred vendor causes an *observed* dispatch to the alternate vendor (ledger-verified), with cost/latency deltas persisted in `checkpoint.json` exactly as `openspec/specs/roadmap-orchestration/spec.md` already specifies; a stuck `dispatch_fn` trips the cap instead of spinning.

### Phase 2 — Durable loops: from mortal sessions to a self-continuing factory

> With routing decisions real and results structured, make the loops survive session death and stop blocking on humans. All items respect the harness-agnostic adapter constraint from §1.3.

#### RI-7: The resume contract (Effort: S, Depends: —)

**What**: Formalize "any fresh session can pick up the loop" as a tested contract, since RI-8's triggers depend on it.
- One entry point per loop — `/autopilot <change-id> --resume` and `/autopilot-roadmap <workspace> --resume` — that needs *zero* conversational context: everything comes from `loop-state.json` / `checkpoint.json` / the coordinator. (Most of this exists; the work is hardening + tests.)
- Add resume-freshness checks: on resume, validate checkpoint against current branch state (has the branch moved? did a human merge meanwhile?) and reconcile or escalate rather than blindly continuing.
- Cover with tests: kill the loop at each phase boundary, resume in a clean process, assert identical end state to an uninterrupted run.

**Acceptance**: a scripted kill-resume test matrix passes for every autopilot phase and roadmap orchestrator step.

#### RI-8: Scheduled continuation — loops that reschedule themselves (Effort: M, Depends: RI-7; RI-6 for the wait-policy hook)

**What**: Give the loops the ability to *come back* — the direct application of the harness loop/trigger primitives.
- **Claude dispatch adapter**: when a phase waits on an async vendor, don't poll in-session — schedule a self-wakeup matched to the vendor's typical turnaround (from the RI-4 registry) and end the turn; on wake, harvest via the RI-3 ledger and continue from checkpoint. Long waits (limit resets) become one-shot triggers at the known reset time — this *implements* the `wait_if_budget_exceeded` policy's "pause until the known reset window" as an active resume instead of a dead session.
- **Recurring drivers**: a nightly "roadmap tick" trigger that fires a fresh session running `/autopilot-roadmap <workspace> --resume` (no-ops cleanly when nothing is ready), and an hourly PR-babysit tick for open autopilot PRs.
- **Non-Claude harnesses**: same contract via plain cron/CI schedule invoking the harness CLI with the resume entry point — the adapter layer decides trigger-vs-cron; SKILL.md text stays neutral.
- Guard rails: every scheduled continuation checks the coordinator for a still-held pause lock / human escalation before doing work; triggers are registered idempotently (list-then-create) and deregistered at roadmap completion (`/archive-roadmap` cleans up).

**Acceptance**: a roadmap started at 9am with a vendor limit hit at 10am completes overnight with zero human re-invocations; the audit log shows the pause, the scheduled resume, and the completion; killing every live session never strands a roadmap in `in_progress` for more than one tick interval.

#### RI-9: Native fan-out for same-vendor parallel work (Effort: M, Depends: RI-3)

**What**: Use harness-native dynamic dispatch where the vendor is the harness itself.
- In the Claude adapter, run review-convergence fan-out and local-parallel work-package DAGs through native background subagents / deterministic workflow pipelines with **schema-enforced structured outputs** bound to `review-findings.schema.json` — validation happens at the tool-call layer (the model retries on mismatch) instead of post-hoc JSON parsing. Per-call model/effort comes from the RI-5 routing decision (reviewer → premium, runner → economy).
- Keep the subprocess `CliVendorAdapter` path for *cross-vendor* diversity (Codex/Gemini reviewers) — vendor diversity is the point of the convergence design and must not collapse into one harness.
- The known `consensus_synthesizer.py` line-range parser bug gets fixed here (schema enforcement upstream makes the parse path simpler), converting convergence checkpoints from "durability only" to actual recovery.

**Acceptance**: a 3-vendor review round dispatches Claude reviewers natively (no subprocess, no stdout parse) and Codex/Gemini via CLI, all landing in one `review-manifest.json`; synthesis crash recovery from `.review-cache/round-N/` works end-to-end.

#### RI-10: The cloud lane — fresh cloud sessions as routable targets (Effort: L, Depends: RI-3, RI-5)

**What**: Make `location: cloud` a first-class router output with clean mechanics, not a `claude --remote` stdout scrape.
- **Dispatch**: for Claude, a cloud dispatch = a fresh isolated cloud session created per task (trigger-based fresh-session-per-fire or the CLI equivalent), receiving a self-contained prompt: change-id, work-package id, branch, and the resume contract entry point. Session bootstrap already exists (`skills/session-bootstrap`); the container replaces worktree isolation (the `EnvironmentProfile` short-circuit already handles this).
- **Result collection**: cloud tasks end in a push + PR on a conventional branch (`openspec/<change-id>--<agent-id>`, already the convention). Collection is event-driven: PR activity subscriptions (CI status, reviews) for Claude-side; the RI-3 ledger for others. `/merge-pull-requests` becomes the *merge* step, not the *discovery* step.
- **Routing rules** (in RI-5's `routing.yaml`): independent work packages of a `FULL`-parallel feature → cloud lane fan-out (N containers beats N worktrees on a laptop); tasks needing local Docker validation or local secrets → local lane; validation-heavy merges stay local per the existing merge-time gate.
- Codex cloud and Jules remain in the cloud lane through their existing CLIs, upgraded to RI-3 structured harvesting — the lane abstraction is vendor-neutral; only mechanics differ per adapter.

**Acceptance**: `/implement-feature` on a 3-package `FULL`-parallel feature routes ≥2 packages to cloud sessions, collects all results as PRs without any in-session polling, and integrates via the existing merge path; the coordinator work queue shows the full lifecycle of every cloud task.

#### RI-11: Non-blocking human gates (Effort: M, Depends: RI-8)

**What**: Turn synchronous human pauses into parked items + notifications, so one blocked item never stalls the factory.
- On ESCALATE / proposal-approval / merge gates: write the approval request to the coordinator's existing approval queue, fire the existing notification channels (Gmail/Telegram/webhook), mark the item `blocked`, and *continue with other ready items* (the roadmap loop already has `_get_ready_items`; the change is to not park the whole loop).
- Approval responses (the notification-token reply path already exists) flip the item back to ready; the next scheduled tick (RI-8) picks it up. No live session needs to be waiting.
- The mandatory human merge gate stays mandatory — this changes *where the human answers* (async, from their phone) not *whether* they're asked.

**Acceptance**: a roadmap with one escalated item completes all independent items unattended; the escalated item resumes within one tick of the human's async approval; time-to-unblock is visible in `agent-metrics`.

### Phase 3 — Close the learning loop

#### RI-12: Turn on the flywheel — scheduled learning pipeline (Effort: S–M, Depends: RI-8 infra; RI-1 for trust)

**What**: The pipeline exists (`collect-transcripts → memory → improve-harness → proposal stub`); schedule it.
- Weekly trigger (or CI cron) running `collect-transcripts --enable` over the week's sessions then `improve-harness`; output lands as a dated report plus coordinator issues (the issue tracker exists) for gaps above a frequency×severity threshold — issues, not silent stubs, so the signal has a place a human actually looks.
- Wire `/prioritize-proposals` to include improve-harness-generated candidates so gap-fixes compete with feature work in one queue.
- Keep the human in the loop where the design put them: proposals still need human refinement; the automation moves the *noticing* from hand-crank to schedule.

**Acceptance**: after a week of normal operation, an unattended run produces a gap report and filed issues; zero manual invocations of the collection pipeline.

#### RI-13: Routing feedback — outcomes shape decisions (Effort: M, Depends: RI-5, RI-6, RI-12)

**What**: Make routing empirical. This is the "learning" half of policy-aware routing that the current regex-nudging `replanner` isn't.
- From the routing records (RI-5) + dispatch ledger (RI-3) + convergence metrics (already emitted to memory), compile a periodic **routing scorecard**: per (vendor × phase-archetype × location): success rate, mean convergence rounds, mean cost, mean latency, limit-hit frequency.
- v1 consumption is conservative and inspectable: the scorecard renders into `routing.yaml` as *advisory weights* a human reviews and commits (same PR discipline as any config change). v2 (explicitly later, gated on data volume): automatic weight updates with bounded step size — a simple empirical-success bandit, never a black box.
- Also fix the roadmap-level learning consumer: replace `replanner.py`'s regex ID-matching with the scorecard + learning entries feeding `route/task` signals for pending items, and give `replan_required` a real handler — a scheduled `/plan-roadmap --replan <workspace>` pass that re-decomposes against the source proposal instead of leaving a documented dead status.

**Acceptance**: the scorecard exists and is regenerated on schedule; at least one routing rule cites scorecard evidence in its rationale; `replan_required` items get automatically re-planned or escalated within one tick, never silently stuck.

#### RI-14: Freshness and retrieval (Effort: M, Depends: RI-1 pattern)

**What**: Extend the decision-index freshness discipline to the remaining generated knowledge, and make retrieval less dependent on agent virtue.
- Staleness gates: CI check (or scheduled refresh trigger) for `docs/architecture-analysis/` and `docs/factory-intelligence/` using their own generated_at metadata and the documented 20-commit threshold — warn in PRs, block only in the skills that *depend* on parallel-zone data (`plan-feature`, `implement-feature` refuse-or-refresh when stale).
- Session-start context injection: extend the SessionStart hook to inject the latest handoff summary + top-K relevant memories for the active change (the hook infra and `register_agent.py` already run there) — retrieval stops depending on the agent remembering Step 0.
- Raise handoff read depth for multi-session threads (`handoffs.py:191` `limit=1` → recent-N with the same bounded-context rules the roadmap spec already defines for learning entries).
- Make `phase_record.write_both()` failures visible: a failed coordinator write with a failed local fallback is an error surfaced at the gate, not a warning — gap capture must not be silently lossy.

**Acceptance**: no skill consumes architecture artifacts older than threshold without an explicit refresh-or-acknowledge; a fresh session on an in-flight change starts with the handoff in context with zero skill invocation.

### Phase 4 — Structure & scale

#### RI-15: Decompose the coordinator monoliths (Effort: L, Depends: best after Phase 1 lands its endpoints)

**What**: `coordination_api.py` (3.3k LOC) and `coordination_mcp.py` (3.2k LOC) into per-domain routers/tool-modules (locks, work, memory, approvals, merge-train, routing, vendors, kanban) over the existing service layer. Mechanical, high-value for review bandwidth and merge-conflict surface — and the routing/vendor endpoints from Phase 1 shouldn't be born into a monolith. Preserve the Dockerfile-COPY contract checks (`check_docker_imports.py`) which get *more* valuable as files multiply.

**Acceptance**: no `src/` module over ~800 LOC; route inventory unchanged (contract-tested before/after); both CI docker guards green.

#### RI-16: Evaluate the router itself (Effort: M, Depends: RI-5, RI-13)

**What**: The router becomes load-bearing infrastructure; test it like one.
- gen-eval scenarios for routing: given synthetic task profiles + registry states (vendor down, limit hit, cost ceiling, secrets-required), assert routing decisions and fallback ladders — the same generator-evaluator harness already used for coordinator behavior.
- Replay evaluation: run historical dispatch records (from the audit log) through proposed `routing.yaml` changes to show decision diffs before merging a routing change — a "routing change PR" shows *what would have routed differently last month*.

**Acceptance**: routing config changes come with a replay diff in the PR; the gen-eval routing suite runs in CI.

---

## Part 3 — Sequencing

### Dependency DAG

```
Phase 0:  RI-1 (drift gates)        RI-2 (versions/docs)
              │ (trust)                  
Phase 1:  RI-3 (structured results) RI-4 (vendor registry)
              │        └──────┬──────────┘
              │             RI-5 (router)
              │        ┌──────┴──────┐
              └──→ RI-6 (orchestrator obeys router)
Phase 2:  RI-7 (resume contract)
              └──→ RI-8 (scheduled continuation) ──→ RI-11 (async human gates)
          RI-3 ──→ RI-9 (native fan-out)
          RI-3, RI-5 ──→ RI-10 (cloud lane)
Phase 3:  RI-8 ──→ RI-12 (learning flywheel) ──→ RI-13 (routing feedback) ←── RI-5, RI-6
          RI-14 (freshness/retrieval)
Phase 4:  RI-15 (decompose monoliths)   RI-16 (router evals) ←── RI-5, RI-13
```

### Suggested order of execution

1. **Now, in parallel**: RI-1, RI-2 (hygiene, independent), RI-7 (resume contract — small and unblocks the most).
2. **The routing arc**: RI-3 → RI-4 → RI-5 → RI-6. This is the highest-value sequence in the roadmap; RI-3 and RI-4 can run in parallel.
3. **The durability arc**: RI-8 → RI-11, with RI-9 and RI-10 in parallel once RI-3/RI-5 land.
4. **The learning arc**: RI-12 → RI-13, RI-14 alongside.
5. **Consolidation**: RI-15, RI-16.

### Quick wins (each ≤ a day, immediate payoff)

- `install.sh --check` + CI drift job (from RI-1).
- `core.hooksPath` wiring (from RI-1).
- Global iteration cap + no-progress detector in the roadmap loop (from RI-6 — extractable early since it needs no router).
- Delete the hardcoded vendor list in `orchestrator.py:317` in favor of `vendor-status` output (down-payment on RI-4).
- Tag `v0.2.0` (from RI-2).
- Lock-release-by-agent endpoint (from RI-3 — closes the documented cloud lock-leak).

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Claude-specific primitives leak into vendor-neutral skills | Hard rule from §1.3: primitives only inside adapters; SKILL.md text stays neutral; RI-16 replay tests run per-adapter |
| Scheduled continuation loops away unattended (runaway triggers) | Every tick checks pause locks + escalations first; iteration caps (RI-6); idempotent trigger registration; `/archive-roadmap` deregisters |
| Router makes confidently wrong decisions | v1 is deterministic YAML rules with rationale strings and audit records; weights change only via reviewed PRs (RI-13); replay diffs before merge (RI-16) |
| Cloud lane produces PR floods | Cloud fan-out gated by routing rules (parallel-zone `FULL` only) and the existing merge-time validation gate; `merge-pull-requests` stays the human-adjacent merge step |
| Refactors (RI-15) collide with feature work | Schedule after Phase 1 endpoints stabilize; contract-test route inventory before/after |

---

## Part 4 — How to execute this roadmap

This document is shaped for the repo's own machinery:

```
/plan-roadmap docs/proposals/repo-improvement-roadmap.md
    → review/adjust the generated roadmap.yaml (items ≈ RI-1..RI-16, deps as above)
    → approve candidates
/autopilot-roadmap openspec/roadmaps/repo-improvement/
```

Two notes for that run:
- Set the roadmap `policy:` block deliberately — `preferred_vendor`, `cost_ceiling_usd`, `default_action: switch_if_time_saved` — since exercising the (currently stubbed) policy path on this very roadmap generates exactly the dispatch-outcome data RI-13 needs.
- Phase 0 + the quick wins are good candidates for `/quick-task`-scale dispatch without full OpenSpec ceremony; everything from RI-3 onward deserves the full proposal → review → implement → validate loop.
