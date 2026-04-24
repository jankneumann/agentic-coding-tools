# Proposal: Symphony-Adoption Roadmap

**Roadmap ID**: symphony
**Status**: Draft
**Created**: 2026-04-24
**Source**: [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
**Companion proposal**: [`openspec/changes/harness-engineering-features/proposal.md`](../../changes/harness-engineering-features/proposal.md)

## Summary

OpenAI's Symphony specifies a long-running orchestration service that polls an issue tracker, creates deterministic per-issue workspaces, dispatches coding-agent subprocesses against a repo-owned `WORKFLOW.md` contract, reconciles against tracker state each tick, and surfaces operator observability — without requiring a persistent database for runtime state. This proposal captures the Symphony concepts that are **not already covered** by our existing coordinator, skills workflow, or the in-flight `harness-engineering-features` change, and decomposes them into a prioritized, phased roadmap.

## Why

Our stack has the *capabilities* Symphony depends on (scope enforcement, DAG scheduling, worktrees, verification phases, multi-vendor review, policy engine), but we lack Symphony's **operational runtime shape**: a continuously running daemon driven by issue-tracker state, with a repo-versioned workflow contract and a uniform agent subprocess protocol. Adding this layer lets us (a) run unattended against GitHub Issues / Linear boards, (b) version agent workflow policy alongside code, and (c) give operators a live state surface for concurrent runs — without giving up the richer intra-feature parallelism, speculative merge trains, and spec-driven gates we already have.

The existing `harness-engineering-features` proposal addresses the *meta-harness* (review loops, context tiering, architecture linters, evaluator separation, throughput metrics). This roadmap is deliberately orthogonal — it addresses the *orchestration runtime*. The two are complementary; the daemon introduced here will call into the harness features as they land.

## Constraints

- **Must preserve existing invariants**: human approval gates on `/plan-feature`, scope enforcement in `scope_checker.py`, worktree isolation, rebase-merge for agent PRs, and the three-level coordination model (intra-feature / cross-feature / cross-application).
- **Must degrade gracefully**: daemon components must run even when the coordinator is unreachable, following the existing `COORDINATOR_AVAILABLE` / capability-flag pattern.
- **Must not lock us to one tracker**: Symphony ships a Linear adapter; we require a GitHub Issues adapter first, with Linear as a parallel implementation behind the same port.
- **Must respect the Codex-vs-Claude-Code-vs-Gemini vendor matrix**: Symphony's Codex JSON-RPC app-server protocol is Codex-specific. Our agent-runner port shall abstract over multiple vendor subprocess protocols.
- **Shall keep runtime state recoverable from tracker + filesystem**: in-memory orchestrator state should survive crashes via re-polling and worktree re-discovery, matching Symphony's design philosophy, even though we retain the coordinator for richer audit and cross-feature coordination.
- **Shall treat trust posture as an artifact**: each deployment must document its approval, sandbox, and network policy explicitly, checked into the repo.

## Capabilities

Each capability below is a candidate OpenSpec change. Headings use H3 so the decomposer treats them as discrete items; `depends on:` hints inform the DAG.

### Symphony-style dispatcher daemon

A long-running service that polls an issue tracker on a fixed cadence, owns a single authoritative in-memory orchestrator state (`running`, `claimed`, `retry_attempts`, `completed`, totals), and dispatches eligible issues under a global concurrency cap. Recovers on restart by re-polling the tracker and reconciling against existing worktrees — no runtime DB required. *Acceptance:* daemon stays up ≥24h unattended, deterministically dispatches ≥50 issues without duplicate dispatch or orphaned workspaces. *Depends on:* (none — foundational).

### WORKFLOW.md repo-owned policy contract

Define a `WORKFLOW.md` format: YAML front matter (typed config — poll interval, concurrency limits, active/terminal states, agent executable/args, workspace hooks, stall timeouts) plus a Jinja-like prompt body with **strict** template semantics (unknown variables/filters raise, never silently fallback). Dynamically reloadable without restarting the daemon. Shall provide a JSON schema and validator. *Acceptance:* schema validation rejects malformed fronts; reload applies within one poll tick. *Depends on:* (none).

### GitHub Issues tracker adapter

Primary adapter for issue-tracker-driven dispatch: fetch candidate issues by label/state, fetch specific issue states for reconciliation, fetch terminal issues at startup for workspace cleanup, normalize to the common `Issue` model (id, identifier, priority, state, labels, blocked_by, timestamps). Uses the GitHub MCP tools we already have. *Acceptance:* parity with Symphony's Linear adapter for the required fetch operations against a test repo. *Depends on:* Symphony-style dispatcher daemon, WORKFLOW.md repo-owned policy contract.

### Linear tracker adapter (parallel implementation)

Port-and-adapter twin of the GitHub adapter, built against Linear's GraphQL API. Demonstrates the tracker-port abstraction holds. *Acceptance:* can swap adapter via `tracker.kind` in `WORKFLOW.md` with no daemon code changes. *Depends on:* GitHub Issues tracker adapter.

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

### Scoped tracker-GraphQL tool for agents

Expose a `tracker_graphql` tool (analog to Symphony's `linear_graphql`) that lets the agent subprocess run scoped GraphQL/REST operations against the active tracker using the daemon's credentials, one operation per call, with an audit-log entry. Primary implementation targets GitHub; Linear variant piggybacks on the Linear adapter. *Acceptance:* agent can transition issue state, post comment, link PR without holding raw credentials. *Depends on:* GitHub Issues tracker adapter.

### Token, rate-limit, and run accounting

Central aggregation of `codex_totals` equivalent: per-run and per-daemon input/output/total tokens, runtime seconds, last rate-limit snapshot from agent events. Surfaced via structured logs with `issue_id`, `issue_identifier`, `session_id` context keys. *Acceptance:* dashboards can answer "tokens burned per issue per day" and "current rate-limit headroom" without log-scraping. *Depends on:* Agent-runner port with vendor adapters.

### Operator HTTP status surface

Optional FastAPI sidecar exposing `/api/v1/state` (current `running`, `claimed`, `retry_attempts`, totals, rate limits), `/api/v1/<issue_id>` (per-issue detail), `/healthz`, `/metrics`. Failures in the status surface must not crash the daemon. *Acceptance:* operator can query live state during long unattended runs; daemon survives sidecar crashes. *Depends on:* Token, rate-limit, and run accounting.

### Trust-posture artifact and deployment-profile binding

Require each deployment to check in a `symphony/TRUST_POSTURE.md` declaring: approval policy (auto / operator-gated / fail-closed), sandbox mode, network allowlist, coordinator trust level, guardrail posture. Bind this artifact to the existing `profiles.py` and `policy_engine.py` so posture is enforceable, not just documented. *Acceptance:* daemon refuses to dispatch when required posture fields are missing or contradict `WORKFLOW.md`. *Depends on:* WORKFLOW.md repo-owned policy contract.

### Daemon ↔ coordinator integration

Wire the daemon into the existing coordinator as a peer: register as an agent via `discovery.py`, acquire lock-namespace claims through `feature_registry.py` on dispatch, write to the audit trail on every state transition, respect guardrails and Cedar policies on pre-flight checks. Daemon must still operate in `COORDINATOR_AVAILABLE=false` degraded mode. *Acceptance:* parallel dispatcher runs do not collide with human-triggered `/implement-feature` runs; audit log shows end-to-end traceability. *Depends on:* Symphony-style dispatcher daemon, Tracker-state reconciliation and stall detection.

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

Deliver the minimum viable Symphony-shaped daemon against GitHub Issues. Items: Symphony-style dispatcher daemon, WORKFLOW.md repo-owned policy contract, GitHub Issues tracker adapter, Issue-keyed workspace manager with lifecycle hooks, Centralized retry queue with exponential backoff.

### Phase 2 — Agent Runtime & Reconciliation

Add vendor-agnostic agent execution, turn-based continuation, stall detection, and scoped tracker tooling. Items: Agent-runner port with vendor adapters, Turn-based session continuation with tracker re-check, Tracker-state reconciliation and stall detection, Scoped tracker-GraphQL tool for agents.

### Phase 3 — Observability & Trust

Add operator-facing surfaces and make trust posture enforceable. Items: Token, rate-limit, and run accounting; Operator HTTP status surface; Trust-posture artifact and deployment-profile binding.

### Phase 4 — Integration & Portability

Tie the daemon into the coordinator and add a second tracker adapter plus harness-readiness auditing. Items: Daemon ↔ coordinator integration, Linear tracker adapter (parallel implementation), Harness-readiness audit for Symphony-compatibility.

## References

- [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
- [OpenAI — Harness engineering](https://openai.com/index/harness-engineering/)
- [`docs/parallel-agentic-development.md`](../../../docs/parallel-agentic-development.md)
- [`openspec/changes/harness-engineering-features/proposal.md`](../../changes/harness-engineering-features/proposal.md)
