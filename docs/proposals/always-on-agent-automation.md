# Always-On Agent Automation on a Dedicated Host

## Context and Goals

Target deployment: a dedicated always-on box (ASUS Ascent GX10) running the coordinator, a dispatcher daemon, and the validation stack, executing `/autopilot` and `/autopilot-roadmap` work unattended with (a) automatic verification, (b) scenario-based validation in the spirit of strongdm/attractor, and (c) daily-or-more-frequent merge sync points.

The codebase is closer to this than it first appears. Already delivered (per the OpenSpec archive and specs):

- **Autopilot state machine** persists `loop-state.json` after every transition and resumes headless (`skills/autopilot/scripts/autopilot.py`); per-phase sub-agent dispatch is vendor-neutral (`phase_agent.py`, `provider_dispatch.py`).
- **Roadmap orchestration** has durable checkpoints, per-item learning logs, and a usage-limit policy engine (wait / switch / fail-closed) (`skills/autopilot-roadmap/scripts/`, `roadmap-orchestration` spec).
- **Merge automation** exists server-side: `MergeWatcher` asyncio loop (auto-rebase, auto-rollback, train ticks) plus a skill-side `merge_watcher.py tick` designed for external schedulers (`merge-infrastructure` spec).
- **Coordinator substrate**: work queue with dependency-aware claims, built-in issue tracker with ready/blocked queries, heartbeat + watchdog (15-min stale detection), approval queue with `request_approval`/`check_approval`, notification service (Gmail/Telegram/webhook with reply-to-approve tokens), event bus, episodic memory, immutable audit log with LLM triage.
- **Validation**: `/validate-feature` 10-phase pipeline, gen-eval scenario framework with holdout manifests and a machine-readable `rework-report.json` loop into `/iterate-on-implementation`, playwright behavioral validator.
- **The `symphony` roadmap** (`openspec/roadmaps/symphony/`) is precisely the always-on dispatcher design — 16 items, all `candidate`, none built.

What blocks unattended operation today is narrow and identifiable:

1. **Human gates are prose, not policy.** The Python loops run to terminal states; the gates live only in SKILL.md text (proposal approval at `skills/autopilot/SKILL.md:209`, the terminal merge STOP at `:605`) and in the separately-invoked `/cleanup-feature`. ESCALATE and `replan_required` states park forever without a human.
2. **Nothing starts sessions.** There is no cron, systemd unit, or scheduled trigger anywhere in the repo; the only time-scheduled automation is Dependabot. The coordinator's watchdog/merge-watcher loops are the only daemons, and they never dispatch dev work.
3. **Sync points are user-invoked by spec.** `skill-workflow` spec ("Main Receives Work Through PR Sync Points") mandates user invocation and an active-agent guard that any live worktree blocks repo-wide.
4. **Worktree/session infra assumes interactive turns.** Heartbeats fire from Stop hooks (turn-driven, not wall-clock); the worktree registry is a single JSON file with last-writer-wins semantics; GC is never scheduled; four staleness clocks disagree (watchdog 15 min, active-agent guard 1 h, lock TTL 2 h, GC 24 h).
5. **Validation is advisory where it matters.** gen-eval, security, e2e, and architecture phases are non-blocking; the holdout gate in `/merge-pull-requests` is warning-only; the semantic LLM-judge is dormant (no `llm_backend` wired); and nothing validates *agent trajectories* — only fixed step sequences against a deployed service.
6. **Known autopilot bugs from a real unattended run** are planned but unimplemented: `fix-autopilot-archetype-and-apply-outcome` (0/59) and `fix-compact-hook-phase-boundary-detection` (0/25).

This proposal sequences the extensions. It deliberately reuses the `symphony` roadmap items where they exist rather than re-deriving them, and adopts three attractor concepts that the codebase lacks: the pluggable **interviewer** abstraction for human gates (auto-approve / queue / callback / console with timeout + default choice), **goal gates** enforced at loop exit, and **cross-vendor scenario parity** runs that validate the agents themselves.

## Guiding Principles

- **Wire before building.** Approval queue, notifications with reply-to-approve, issue tracker, merge watcher, and status reporting all exist; most of Phase 1–3 is composition, not new services.
- **Gates become policy objects.** Every human gate gets a machine-readable disposition per trust posture: `auto`, `notify_with_timeout` (default action on expiry), or `block`. Prose instructions stop being the enforcement mechanism.
- **The human merge gate stays the default.** Automation first widens throughput (scheduled sync windows with notification + veto window); full auto-merge is a posture the operator opts into per-repo, never a side effect.
- **Fail closed, notify always.** Every unattended decision writes audit + emits a notification event; ambiguity parks work as `blocked` rather than guessing.
- **Validate the product and the agents.** gen-eval/holdout gates cover the system under test; a new trajectory harness covers the harness itself, attractor-style.

## Phase 0 — Land the Prerequisites

### Capability: Implement the Two Autopilot Correctness Fixes

Implement the already-reviewed `fix-autopilot-archetype-and-apply-outcome` and `fix-compact-hook-phase-boundary-detection` changes. Both bugs were hit during the real unattended `/autopilot extract-gen-eval-package` run; clean unattended loops are impossible while VALIDATE resolves to a read-only archetype and sub-agents can skip phases via `apply-outcome`.

Acceptance outcomes:
- Both active changes reach implemented status and pass `/validate-feature`.
- A re-run of the failure scenario in each proposal no longer reproduces.

### Capability: Flush the Implemented-Not-Archived Backlog

Finish and archive `factory-missions-architecture-alignment` (51/53) and `extract-gen-eval-package` (38/43) so the changes/ directory reflects reality before a daemon starts consuming it as a work source.

Acceptance outcomes:
- Both changes archived; `openspec/changes/` contains only genuinely open work.

## Phase 1 — Trust Posture and Approval Gates

### Capability: Trust Posture Contract

Adopt the symphony `trust-posture-binding` item now rather than at P12. A repo-owned `TRUST_POSTURE.md` (typed YAML front matter) declares, per gate, one of `auto | notify_with_timeout | block`, plus timeout and default action. Gates enumerated: GATEKEEPER escalation, proposal approval, plan-review convergence failure, validation failure, ESCALATE resume, `replan_required`, PR creation, merge. Hot-reloadable; absence of the file means every gate is `block` (today's behavior).

Acceptance outcomes:
- Schema-validated contract file; unknown gate names or dispositions fail validation.
- With no contract present, behavior is byte-identical to today.

### Capability: Approval Gate Service (Interviewer Abstraction)

A small library (`skills/shared/approval_gate.py`) modeled on attractor's Interviewer interface: given a gate name and context, it (1) consults the trust posture, (2) on `auto` logs and proceeds, (3) on `notify_with_timeout` files a coordinator approval (`request_approval`), pushes a notification (Telegram reply-to-approve tokens already exist), polls `check_approval` until timeout, then applies the default action, (4) on `block` parks the loop state and exits cleanly for later resume. Degrades to `block` when the coordinator is unreachable.

Acceptance outcomes:
- All four dispositions covered by tests, including coordinator-down degradation.
- Every gate decision (auto or defaulted) lands in the audit log with the posture that authorized it.

### Capability: Encode Autopilot Gates in Code

Move the prose gates into `autopilot.py`: PLAN proposal approval, the SUBMIT_PR→DONE merge handoff, ESCALATE resume, and roadmap `replan_required` (which additionally gains an automated path: re-invoke `/plan-roadmap` in replan mode when posture allows). Goal-gate check at DONE, attractor-style: DONE is refused unless VALIDATE/VAL_REVIEW phase records show pass status — validation success becomes structurally required, not just sequentially prior.

Acceptance outcomes:
- Grep of `skills/autopilot/SKILL.md` finds no gate whose only enforcement is prose.
- An unattended run with an `auto`-everything posture reaches SUBMIT_PR without interaction; with the default posture it parks exactly where it does today.
- A run whose VALIDATE record is missing or failed cannot reach DONE.

## Phase 2 — Dispatcher Daemon on the Always-On Host

### Capability: Dispatcher Daemon (symphony P1 + P3)

Build the symphony `dispatcher-daemon` and `coordinator-tracker-adapter` items: a long-running service (systemd unit on the GX10) polling the coordinator issue tracker's ready-issues query on a fixed cadence, dispatching headless sessions (`claude -p` / vendor CLI adapters running `/autopilot <change-id>` or `/autopilot-roadmap <roadmap>`), enforcing a global concurrency cap, and recovering orchestrator state after restart purely from tracker + worktree + `loop-state.json` state (no runtime DB). Each spawned session gets a distinct `AGENT_ID` so heartbeats and handoffs don't collide (handoff reads are currently "most recent globally" — the daemon must pass explicit agent names).

Acceptance outcomes:
- Symphony acceptance criteria hold: 24 h unattended without leaked workspaces; ≥50 issues processed with no duplicate dispatch.
- Kill -9 of the daemon followed by restart resumes every in-flight item from its checkpoint without re-dispatch.
- Sessions are spawned with unique agent identities visible in `discover_agents`.

### Capability: Wall-Clock Heartbeat and Worktree Hardening

Fix the interactive-session assumptions: (1) the daemon heartbeats every active session's worktree on a wall-clock timer (heartbeats today fire only from Stop hooks, so a long non-interactive phase looks dead to the 15-min watchdog and the 1-h sync-point guard); (2) `worktree.py gc` runs on a timer; (3) the registry gains `flock`-based locking or per-entry files (single-file atomic-replace loses concurrent updates); (4) the four staleness clocks (15 min / 1 h / 2 h / 24 h) are documented and reconciled against daemon cadences.

Acceptance outcomes:
- A 3-hour non-interactive phase is never flagged stale by watchdog or sync-point guard.
- 20 concurrent setup/heartbeat/teardown operations lose zero registry updates.
- Stale worktree count on the daemon host is bounded over a 7-day soak.

### Capability: Rate-Limit Accounting and Vendor Arbitrage

Land the existing `cross-vendor-arbitrage-instrument` proposal here: durable cost/quota/ToS signal layer feeding the roadmap policy engine, replacing the hardcoded cost tiers in `policy.py:221-241` and the placeholder vendor list in `orchestrator.py:319`. The daemon is the natural producer of `cost_observed_usd` / `latency_observed_seconds` learning-log fields, which are defined but empty today.

Acceptance outcomes:
- Policy decisions (wait/switch/fail-closed) use observed signals, not stubs.
- Learning-log cost/latency fields populate on every daemon-dispatched item.

## Phase 3 — Scheduled Merge Sync Points

### Capability: Spec Amendment — Policy-Authorized Sync Windows

Amend the `skill-workflow` "Main Receives Work Through PR Sync Points" requirement: sync-point skills MAY also run under a scheduled sync window declared in the trust posture (cadence, allowed sources, auto-merge ceiling), with the active-agent guard and validation gates unchanged. This is a deliberate, reviewed relaxation of "MUST be user-invoked" — scoped to the posture file so interactive repos are unaffected.

Acceptance outcomes:
- `openspec validate` passes with the amended requirement; the user-invoked path remains the default.

### Capability: Headless Sync Execution

`/expedite` already produces a machine-readable READY/BLOCKED verdict (active agents + `pre_merge_gate` + rework report); add a headless mode to `/merge-pull-requests` that consumes it: non-interactive triage using the existing classification scripts, merging only PRs that are Fresh, CI-green, validation-gated, and within the posture's auto-merge ceiling (e.g., dependabot + autopilot PRs with passing holdout gates), notifying-with-veto-window for everything else. The existing `--pipeline` post-merge machinery (metrics, auto-rebase ≤5 PRs, 15-min rollback monitor) makes unattended merging recoverable.

Acceptance outcomes:
- A scheduled run merges qualifying PRs end-to-end with zero prompts and posts a merge-log digest notification.
- A PR outside the ceiling is never merged unattended; it produces an approval request instead.
- An induced main-CI failure after an unattended merge triggers the existing auto-rollback path.

### Capability: Quiet-Window Drain Protocol

The dispatcher coordinates the sync window: stop dispatching, let active sessions drain (bounded wait, pinning long-runners for the next window), run `/expedite` → headless merge → cascading rebase of surviving branches, then resume dispatch. This resolves the deadlock where a daemon that keeps sessions perpetually alive would permanently block the repo-global active-agent guard.

Acceptance outcomes:
- Daily (configurable, up to hourly) windows execute on the GX10 for a week with no guard `--force` overrides and no orphaned rebases.
- Dispatch throughput before/after windows shows drain-and-resume works (no starved queue).

## Phase 4 — Scenario-Based Validation

### Capability: Blocking Behavioral Gates

Promote the existing behavioral machinery from advisory to enforcing at sync points: (1) the holdout gate in `/merge-pull-requests` (currently warning-only) becomes blocking under scheduled windows; (2) `validate-feature` wires an `llm_backend` so gen-eval `SemanticBlock` judges actually run instead of silently skipping; (3) the posture file declares which validation phases are merge-blocking per repo (today only smoke + task-drift block).

Acceptance outcomes:
- A holdout scenario failure blocks an unattended merge and files an approval request.
- Semantic evaluations report pass/fail (not skip) in a default GX10 run.

### Capability: Agent Trajectory Scenario Harness

The genuinely new attractor-inspired piece. Today gen-eval validates fixed transport-level step sequences against a deployed service; nothing validates the *agents*. Add a harness (new `packages/agent-scenarios/`) where a scenario YAML defines: a task prompt, a fixture repo state, the skill under test, and goal gates (expected file/branch/PR/artifact outcomes plus prohibited side effects — reusing gen-eval's `ExpectBlock`/`SideEffectsBlock` vocabulary). The runner executes the scenario headless per vendor (attractor's cross-provider parity matrix), scores goal gates deterministically plus an LLM-judge trajectory review over the collected transcript (`collect-transcripts` adapters already normalize these), and emits `review-findings.schema.json` findings. Run nightly on the GX10; failures feed the existing capability-gap pipeline (`/improve-harness`). Harness/skill changes must pass the parity suite before the dispatcher routes real work through them.

Acceptance outcomes:
- ≥10 seed scenarios covering plan/implement/validate/merge skills run nightly across ≥2 vendors.
- A deliberately-broken skill change fails the suite and produces a capability-gap finding.
- Scenario results are queryable per vendor per skill over time (regression trend).

### Capability: Incident Auto-Seeding

Close the regression loop automatically: auto-rollbacks, ESCALATE exits, and confirmed holdout failures generate `bootstrap_from_incident` scenario seeds (holdout visibility) instead of relying on manual seeding — today an un-reported escaped defect has no holdout scenario and can regress silently.

Acceptance outcomes:
- Every auto-rollback event yields a draft holdout scenario linked to the incident.

## Phase 5 — Operator Surface and Learning Loop

### Capability: Operator Status Surface

Symphony's `operator-http-status-surface` (`/api/v1/state`, `/healthz`, `/metrics` sidecar) or an extension of kanban-viz: live view of daemon queue depth, in-flight sessions and phases, gate decisions awaiting approval, next sync window, and vendor budget state. Note the existing coupling: `/sync-points/status` reads `.git-worktrees/.registry.json` off local disk, so the coordinator API must run on the same host as the checkout (satisfied by the single-box GX10 layout; must be fixed before splitting hosts).

Acceptance outcomes:
- One URL answers "what is the daemon doing right now and what is it waiting on."

### Capability: Scheduled Learning and Metrics

Put the existing analysis skills on timers: `agent-metrics` (throughput/failure/gap reports from audit + episodic memory), `collect-transcripts` triage, `scripts/ai_dora_snapshot.py`, and the `usage-stats-multi-model` proposal for cross-vendor cost visibility. Adopt the `ambient-review-ledger` proposal as the continuous commit-granular review sensor feeding sync-point gates.

Acceptance outcomes:
- Weekly automated harness-health digest delivered via the notification service.

## Appendix: Attractor Concept Mapping

| attractor concept | repo status | action |
|---|---|---|
| Checkpoint after every node | `loop-state.json` / `checkpoint.json` — equivalent, delivered | none |
| DOT-graph declared pipeline | hardcoded `TRANSITIONS` table | none (sufficient; declarative graphs optional later) |
| Interviewer abstraction (auto/console/callback/queue) + timeout + default choice | missing — gates are prose | Phase 1 approval gate service |
| Goal gates at exit | missing — DONE doesn't verify validation records | Phase 1 gate encoding |
| Retry policies + retry_target routing | convergence loop (3 rounds, stall/quorum detection) covers reviews; symphony `retry-queue-backoff` covers dispatch | Phase 2 daemon |
| Model stylesheet | `archetypes.yaml` phase→archetype→tier — equivalent, delivered | none |
| Cross-provider scenario parity matrix | missing — gen-eval tests the SUT, not agents | Phase 4 trajectory harness |
| Non-interactive "software factory" runner | missing — no scheduler exists | Phase 2 dispatcher daemon |

## Appendix: GX10 Host Layout

Single box runs: ParadeDB + coordinator API (`docker-compose --profile api`; watchdog + merge-watcher come up with it), the dispatcher daemon (systemd), Docker for `validate-feature` deploy/smoke/e2e phases, and Playwright/Node for frontend validation. Coordinator and repo checkout co-located (required by the sync-point registry coupling above). The GB10's unified memory also makes the box a candidate to serve a local model as an economy-tier vendor for triage/review work once the Phase 2 arbitrage signal layer exists — a cost-free consumer for the vendor router.
