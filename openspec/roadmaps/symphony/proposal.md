# Proposal: Symphony-Adoption Roadmap

**Roadmap ID**: symphony
**Status**: Draft
**Created**: 2026-04-24
**Source**: [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
**Companion proposal**: [`openspec/changes/harness-engineering-features/proposal.md`](../../changes/harness-engineering-features/proposal.md)

## Summary

OpenAI's Symphony specifies a long-running orchestration service that polls an issue tracker, creates deterministic per-issue workspaces, dispatches coding-agent subprocesses against a repo-owned `WORKFLOW.md` contract, reconciles against tracker state each tick, and surfaces operator observability — without requiring a persistent database for runtime state. This proposal captures the Symphony concepts that are **not already covered** by our existing coordinator, skills workflow, or the in-flight `harness-engineering-features` change, and decomposes them into a prioritized, phased roadmap.

## Why

Our stack has the *capabilities* Symphony depends on (scope enforcement, DAG scheduling, worktrees, verification phases, multi-vendor review, policy engine), but we lack Symphony's **operational runtime shape**: a continuously running daemon driven by issue-tracker state, with a repo-versioned workflow contract and a uniform agent subprocess protocol. Adding this layer lets us (a) run unattended against the tracker we already host, (b) version agent workflow policy alongside code, and (c) give operators a live state surface for concurrent runs — without giving up the richer intra-feature parallelism, speculative merge trains, and spec-driven gates we already have.

**Canonical tracker is the coordinator.** The coordinator already ships a built-in issue tracker (`agent-coordinator/src/issue_service.py` built on `work_queue` extensions from migration `017_issue_tracking.sql`, the beads-replacement work). It carries everything the daemon needs — labels, `issue_type`, `parent_id` for epics, `depends_on` UUID arrays for blockers, status mapped onto the existing work-queue lifecycle (`open→pending`, `in_progress→running`, `closed→completed`), and automatic audit capture. Pointing the daemon at this built-in tracker means the tracker layer is reachable via the same MCP/HTTP transport the daemon already uses for locks and audit, with no external API quotas, no tokens, no webhook infrastructure, and no drift-sync problem. GitHub Issues (and Linear) become *optional external projections* for human visibility and PR-linking, never the source of truth.

The existing `harness-engineering-features` proposal addresses the *meta-harness* (review loops, context tiering, architecture linters, evaluator separation, throughput metrics). This roadmap is deliberately orthogonal — it addresses the *orchestration runtime*. The two are complementary; the daemon introduced here will call into the harness features as they land.

## Constraints

- **Must preserve existing invariants**: human approval gates on `/plan-feature`, scope enforcement in `scope_checker.py`, worktree isolation, rebase-merge for agent PRs, and the three-level coordination model (intra-feature / cross-feature / cross-application).
- **Must degrade gracefully**: daemon components must run even when the coordinator is unreachable, following the existing `COORDINATOR_AVAILABLE` / capability-flag pattern.
- **Canonical tracker shall be the coordinator's built-in `issue_service`.** External tracker adapters (GitHub Issues, Linear) are optional one-way projections from the coordinator outward; the daemon never polls or reads back from them.
- **Port-and-adapter pattern shall be preserved**: tracker projections plug into the same port, proving the abstraction with ≥2 implementations (GitHub + Linear).
- **Must respect the Codex-vs-Claude-Code-vs-Gemini vendor matrix**: Symphony's Codex JSON-RPC app-server protocol is Codex-specific. Our agent-runner port shall abstract over multiple vendor subprocess protocols.
- **Shall keep runtime state recoverable from tracker + filesystem**: in-memory orchestrator state should survive crashes via re-polling the coordinator and re-discovering worktrees, matching Symphony's design philosophy.
- **Shall treat trust posture as an artifact**: each deployment must document its approval, sandbox, and network policy explicitly, checked into the repo.

## Capabilities

Each capability below is a candidate OpenSpec change. Headings use H3 so the decomposer treats them as discrete items; `depends on:` hints inform the DAG.

### Symphony-style dispatcher daemon

A long-running service that polls an issue tracker on a fixed cadence, owns a single authoritative in-memory orchestrator state (`running`, `claimed`, `retry_attempts`, `completed`, totals), and dispatches eligible issues under a global concurrency cap. Recovers on restart by re-polling the tracker and reconciling against existing worktrees — no runtime DB required. *Acceptance:* daemon stays up ≥24h unattended, deterministically dispatches ≥50 issues without duplicate dispatch or orphaned workspaces. *Depends on:* (none — foundational).

### WORKFLOW.md repo-owned policy contract

Define a `WORKFLOW.md` format: YAML front matter (typed config — poll interval, concurrency limits, active/terminal states, agent executable/args, workspace hooks, stall timeouts) plus a Jinja-like prompt body with **strict** template semantics (unknown variables/filters raise, never silently fallback). Dynamically reloadable without restarting the daemon. Shall provide a JSON schema and validator. *Acceptance:* schema validation rejects malformed fronts; reload applies within one poll tick. *Depends on:* (none).

### Coordinator-native issue tracker adapter (primary)

Primary tracker adapter pointed at the coordinator's built-in `issue_service` (from the beads replacement: `agent-coordinator/src/issue_service.py` + migration `017_issue_tracking.sql`). Reads candidate issues over MCP/HTTP using existing `work_queue` extensions (labels, `issue_type`, `parent_id`, `depends_on` UUIDs, assignee, metadata). Status mapping `open→pending`, `in_progress→running`, `closed→completed` reuses the work-queue lifecycle. Reconciliation and terminal-state fetches route through the same transport the daemon already uses for locks, audit, and guardrails. No external API quotas or tokens required. *Acceptance:* daemon polls coordinator issues via the same MCP/HTTP path as other primitives; labels-based eligibility (e.g. `ready-for-agent`) and `depends_on` UUID blockers are respected; status transitions flow through `issue_service` and are captured in `audit_log`; works in coordinator-degraded mode per `CAN_QUEUE_WORK`. *Depends on:* Symphony-style dispatcher daemon, WORKFLOW.md repo-owned policy contract.

### Issue-keyed workspace manager with lifecycle hooks

Extend `skills/worktree/scripts/worktree.py` so workspaces can be keyed by sanitized issue identifier (`[A-Za-z0-9._-]`) in addition to change-id. Add configurable lifecycle hooks (`after_create`, `before_run`, `after_run`, `before_remove`) with per-hook timeouts; `after_run` failures are logged and ignored (forward-progress invariant). Enforce strict path-containment — workspace path must have configured root as prefix. *Acceptance:* hook invocation order and failure semantics match Symphony SPEC §3. *Depends on:* WORKFLOW.md repo-owned policy contract.

### Centralized retry queue with exponential backoff

Promote retry handling out of individual skills into a first-class queue owned by the daemon: `retry_attempts[issue_id] = {attempt, due_at_ms, timer_handle, error}` with `min(10s × 2^(attempt-1), max_retry_backoff_ms)`. Retry eligibility re-checks tracker state before dispatch. *Acceptance:* deterministic backoff schedule, no retry-storm on flapping tracker states. *Depends on:* Symphony-style dispatcher daemon.

### Agent-runner port with vendor adapters

Define a vendor-agnostic agent-runner port: `start(workspace, prompt) -> session`, `stream_events() -> Iterator[Event]`, `cancel()`, with normalized event types (`turn_started`, `turn_completed`, `token_update`, `rate_limit`, `approval_request`, `user_input_requested`). Ship three adapters: Codex (JSON-RPC app-server over stdio, matches Symphony), Claude Code CLI, and Gemini CLI. Treat `user_input_requested` as a hard fail to prevent hangs. *Acceptance:* same daemon drives all three vendors against the same `WORKFLOW.md`. *Depends on:* Symphony-style dispatcher daemon, WORKFLOW.md repo-owned policy contract.

### Turn-based session continuation with tracker re-check

Within one worker lifetime, stay on the same thread/workspace across up to `agent.max_turns`, re-checking tracker state between turns. If the issue transitions to a non-eligible state mid-run, gracefully stop and surface a reconciliation event. *Acceptance:* stopping mid-run preserves workspace and writes a structured `run_aborted` event. *Depends on:* Agent-runner port with vendor adapters.

### Tracker-state reconciliation and stall detection

Each poll tick: stop active runs whose issues transitioned to terminal/inactive; detect stalled sessions via inactivity timeout and kill+retry; clean workspaces for terminal issues at startup. Shall also reconcile against worktree registry to GC orphans. *Acceptance:* stalled runs are killed within `stall_timeout_ms`; terminal-state workspaces are cleaned on next startup. *Depends on:* Centralized retry queue with exponential backoff, Issue-keyed workspace manager with lifecycle hooks.

### Scoped coordinator-issue tool for agents

Agent-callable tool that wraps `issue_service` operations (transition status, add comment, link PR URL, adjust labels) via the coordinator's MCP/HTTP surface. One scoped operation per call, each automatically captured in `audit_log`. Replaces Symphony's `linear_graphql` with a coordinator-native path so agents never hold raw tracker credentials. External projections (GitHub/Linear) receive these changes through their one-way sync, not through the agent tool. *Acceptance:* agent can transition issue state, post comment, and link PR without external credentials; every invocation writes one `audit_log` entry with `issue_id` and `session_id`; operation surface is intersected with the agent's trust profile. *Depends on:* Coordinator-native issue tracker adapter (primary).

### Token, rate-limit, and run accounting

Central aggregation of `codex_totals` equivalent: per-run and per-daemon input/output/total tokens, runtime seconds, last rate-limit snapshot from agent events. Surfaced via structured logs with `issue_id`, `issue_identifier`, `session_id` context keys. *Acceptance:* dashboards can answer "tokens burned per issue per day" and "current rate-limit headroom" without log-scraping. *Depends on:* Agent-runner port with vendor adapters.

### Operator HTTP status surface

Optional FastAPI sidecar exposing `/api/v1/state` (current `running`, `claimed`, `retry_attempts`, totals, rate limits), `/api/v1/<issue_id>` (per-issue detail), `/healthz`, `/metrics`, plus a human-readable issues view rendered directly from the coordinator-native tracker adapter. Failures in the status surface must not crash the daemon. This is the UI layer that substitutes for an external tracker when teams choose not to deploy a projection. *Acceptance:* operator can query live state during long unattended runs; issues view lists coordinator issues with label/status filters; daemon survives sidecar crashes. *Depends on:* Token, rate-limit, and run accounting.

### Trust-posture artifact and deployment-profile binding

Require each deployment to check in a `symphony/TRUST_POSTURE.md` declaring: approval policy (auto / operator-gated / fail-closed), sandbox mode, network allowlist, coordinator trust level, guardrail posture. Bind this artifact to the existing `profiles.py` and `policy_engine.py` so posture is enforceable, not just documented. *Acceptance:* daemon refuses to dispatch when required posture fields are missing or contradict `WORKFLOW.md`. *Depends on:* WORKFLOW.md repo-owned policy contract.

### Daemon and coordinator peer integration

Beyond the tracker adapter (which is already coordinator-native), wire the daemon into the coordinator's *other* primitives: register via `discovery.py`, acquire lock-namespace claims through `feature_registry.py` on dispatch, write to the audit trail on every state transition, respect guardrails and Cedar policies on pre-flight checks. Daemon must still operate in `COORDINATOR_AVAILABLE=false` degraded mode per capability flags. *Acceptance:* parallel dispatcher runs do not collide with human-triggered `/implement-feature` runs; audit log shows end-to-end traceability; degrades gracefully when coordinator is unreachable. *Depends on:* Symphony-style dispatcher daemon, Tracker-state reconciliation and stall detection.

### GitHub Issues external projection (optional)

One-way projection from coordinator issues to GitHub Issues for external visibility, human UI, and PR↔issue linking. Runs out of process (e.g. triggered by `/prioritize-proposals` or on `issue_service` state change). Never reads back from GitHub; coordinator remains the source of truth. Keeps the port-and-adapter pattern intact and reuses the GitHub MCP tools we already have. *Acceptance:* coordinator issue changes appear as GitHub issue updates within N seconds; no back-sync path; projection failures do not block the daemon or coordinator. *Depends on:* Coordinator-native issue tracker adapter (primary).

### Linear Issues external projection (optional)

Linear counterpart to the GitHub projection. Same one-way semantics: coordinator is canonical, Linear is a downstream mirror. Demonstrates the external-projection port holds across trackers. *Acceptance:* swap projection targets via `WORKFLOW.md` config with no daemon code changes; feature parity with the GitHub projection for required fields. *Depends on:* Coordinator-native issue tracker adapter (primary).

### Harness-readiness audit for Symphony-compatibility

A `/harness-audit` (or extension of `bug-scrub`) that scores a target repo against Symphony's implicit prerequisites: hermetic tests, machine-readable build/test/deploy docs, `WORKFLOW.md` present and valid, `TRUST_POSTURE.md` present, `openspec/` initialized, and side-effect density from `refresh-architecture`. Outputs a go/no-go report with remediation hints. *Acceptance:* report flags at least the five categories above with actionable suggestions. *Depends on:* WORKFLOW.md repo-owned policy contract, Trust-posture artifact and deployment-profile binding.

## Out of Scope

- Re-implementing coordinator primitives (locks, work queue, memory) that Symphony does not have — we keep ours.
- Replacing `/plan-feature` and the human approval gates — Symphony's fire-and-forget model is deliberately not adopted.
- Replacing the speculative merge train — Symphony has nothing equivalent; ours stays.
- Porting to Elixir/BEAM — we take the architectural lessons, not the runtime.
- Duplicating items already scoped in `harness-engineering-features` (review loops, context tiering, architecture linters, evaluator separation, throughput metrics). Where this roadmap touches them, it integrates rather than reimplements.

## Phases

Phase boundaries inform default ordering; the decomposer may adjust based on explicit `depends_on` hints above.

### Phase 1 — Contract & Daemon Foundation

Deliver the minimum viable Symphony-shaped daemon pointed at the coordinator-native tracker. Items: Symphony-style dispatcher daemon, WORKFLOW.md repo-owned policy contract, Coordinator-native issue tracker adapter (primary), Issue-keyed workspace manager with lifecycle hooks, Centralized retry queue with exponential backoff.

### Phase 2 — Agent Runtime & Reconciliation

Add vendor-agnostic agent execution, turn-based continuation, stall detection, and the coordinator-issue tool for agents. Items: Agent-runner port with vendor adapters, Turn-based session continuation with tracker re-check, Tracker-state reconciliation and stall detection, Scoped coordinator-issue tool for agents.

### Phase 3 — Observability & Trust

Add operator-facing surfaces (including the built-in issues view that substitutes for an external tracker UI) and make trust posture enforceable. Items: Token, rate-limit, and run accounting; Operator HTTP status surface; Trust-posture artifact and deployment-profile binding.

### Phase 4 — Integration & External Projections

Tie the daemon into the coordinator's other primitives and ship optional external-tracker projections for human visibility. Items: Daemon and coordinator peer integration, GitHub Issues external projection (optional), Linear Issues external projection (optional), Harness-readiness audit for Symphony-compatibility.

## References

- [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
- [OpenAI — Harness engineering](https://openai.com/index/harness-engineering/)
- [`docs/parallel-agentic-development.md`](../../../docs/parallel-agentic-development.md)
- [`openspec/changes/harness-engineering-features/proposal.md`](../../changes/harness-engineering-features/proposal.md)
