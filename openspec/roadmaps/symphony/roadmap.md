# Roadmap: symphony

> Source: `openspec/roadmaps/symphony/proposal.md` | Status: **planning** | Items: 15


<!-- GENERATED: begin phase-table -->
## Phase Table

| Priority | Item | Effort | Status | Dependencies |
|----------|------|--------|--------|--------------|
| 1 | Symphony-style dispatcher daemon | M | candidate | - |
| 2 | WORKFLOW.md repo-owned policy contract | M | candidate | - |
| 3 | GitHub Issues tracker adapter | M | candidate | dispatcher-daemon, workflow-md-contract |
| 4 | Issue-keyed workspace manager with lifecycle hooks | M | candidate | workflow-md-contract |
| 5 | Centralized retry queue with exponential backoff | S | candidate | dispatcher-daemon |
| 6 | Agent-runner port with vendor adapters | L | candidate | dispatcher-daemon, workflow-md-contract |
| 7 | Turn-based session continuation with tracker re-check | M | candidate | agent-runner-port |
| 8 | Tracker-state reconciliation and stall detection | M | candidate | retry-queue-backoff, workspace-manager-hooks |
| 9 | Scoped tracker-GraphQL tool for agents | S | candidate | github-tracker-adapter |
| 10 | Token, rate-limit, and run accounting | S | candidate | agent-runner-port |
| 11 | Operator HTTP status surface | S | candidate | token-ratelimit-accounting |
| 12 | Trust-posture artifact and deployment-profile binding | M | candidate | workflow-md-contract |
| 13 | Daemon and coordinator integration | M | candidate | dispatcher-daemon, reconciliation-stall-detection |
| 14 | Linear tracker adapter (parallel implementation) | S | candidate | github-tracker-adapter |
| 15 | Harness-readiness audit for Symphony-compatibility | S | candidate | workflow-md-contract, trust-posture-binding |
<!-- GENERATED: end phase-table -->


<!-- GENERATED: begin dependency-dag -->
## Dependency Graph

```mermaid
graph TD
    dispatcher-daemon["Symphony-style dispatcher daemon"]
    workflow-md-contract["WORKFLOW.md repo-owned policy contract"]
    github-tracker-adapter["GitHub Issues tracker adapter"]
    workspace-manager-hooks["Issue-keyed workspace manager with lifec"]
    retry-queue-backoff["Centralized retry queue with exponential"]
    agent-runner-port["Agent-runner port with vendor adapters"]
    turn-based-continuation["Turn-based session continuation with tra"]
    reconciliation-stall-detection["Tracker-state reconciliation and stall d"]
    tracker-graphql-tool["Scoped tracker-GraphQL tool for agents"]
    token-ratelimit-accounting["Token, rate-limit, and run accounting"]
    operator-http-status-surface["Operator HTTP status surface"]
    trust-posture-binding["Trust-posture artifact and deployment-pr"]
    coordinator-integration["Daemon and coordinator integration"]
    linear-tracker-adapter["Linear tracker adapter (parallel impleme"]
    harness-readiness-audit["Harness-readiness audit for Symphony-com"]
    dispatcher-daemon --> github-tracker-adapter
    workflow-md-contract --> github-tracker-adapter
    workflow-md-contract --> workspace-manager-hooks
    dispatcher-daemon --> retry-queue-backoff
    dispatcher-daemon --> agent-runner-port
    workflow-md-contract --> agent-runner-port
    agent-runner-port --> turn-based-continuation
    retry-queue-backoff --> reconciliation-stall-detection
    workspace-manager-hooks --> reconciliation-stall-detection
    github-tracker-adapter --> tracker-graphql-tool
    agent-runner-port --> token-ratelimit-accounting
    token-ratelimit-accounting --> operator-http-status-surface
    workflow-md-contract --> trust-posture-binding
    dispatcher-daemon --> coordinator-integration
    reconciliation-stall-detection --> coordinator-integration
    github-tracker-adapter --> linear-tracker-adapter
    workflow-md-contract --> harness-readiness-audit
    trust-posture-binding --> harness-readiness-audit
```
<!-- GENERATED: end dependency-dag -->


<!-- GENERATED: begin item-details -->
## Item Details

### dispatcher-daemon: Symphony-style dispatcher daemon

- **Status**: candidate
- **Priority**: 1
- **Effort**: M

Long-running service that polls a tracker on a fixed cadence, owns a single authoritative in-memory orchestrator state (running, claimed, retry_attempts, completed, totals), and dispatches eligible issues under a global concurrency cap. Recovers on restart from tracker state + worktree re-discovery without a runtime DB.

**Acceptance outcomes**:
- [ ] Daemon stays up >=24h unattended without leaking workspaces
- [ ] Deterministically dispatches >=50 issues with no duplicate dispatch
- [ ] Restart recovers running set from tracker + filesystem state

### workflow-md-contract: WORKFLOW.md repo-owned policy contract

- **Status**: candidate
- **Priority**: 2
- **Effort**: M

YAML front matter (typed runtime config) plus Jinja-like prompt body with strict template semantics (unknown variables/filters fail loudly). Dynamically reloadable without restart. Ships with a JSON schema and validator.

**Acceptance outcomes**:
- [ ] JSON schema rejects malformed fronts with actionable errors
- [ ] Strict template engine raises on unknown variable or filter
- [ ] Reload applies within one poll tick without restarting the daemon

### github-tracker-adapter: GitHub Issues tracker adapter

- **Status**: candidate
- **Priority**: 3
- **Effort**: M
- **Depends on**: `dispatcher-daemon`, `workflow-md-contract`

Primary tracker adapter: fetch candidate issues by label/state, fetch specific states for reconciliation, fetch terminal issues at startup for cleanup, normalize to the common Issue model (id, identifier, priority, state, labels, blocked_by, timestamps). Uses existing GitHub MCP tooling.

**Acceptance outcomes**:
- [ ] Parity with Symphony's Linear adapter for required fetch operations
- [ ] Normalized Issue model validated against shared schema
- [ ] State comparisons are case-insensitive (lowercase normalization)

### workspace-manager-hooks: Issue-keyed workspace manager with lifecycle hooks

- **Status**: candidate
- **Priority**: 4
- **Effort**: M
- **Depends on**: `workflow-md-contract`

Extend worktree.py to key workspaces by sanitized issue identifier ([A-Za-z0-9._-]) in addition to change-id. Add after_create, before_run, after_run, before_remove hooks with per-hook timeouts. Enforce strict path-containment; after_run failures are logged and ignored.

**Acceptance outcomes**:
- [ ] Hook invocation order matches Symphony SPEC section 3
- [ ] after_run failures do not block forward progress
- [ ] Path containment violations fail closed before agent launch

### retry-queue-backoff: Centralized retry queue with exponential backoff

- **Status**: candidate
- **Priority**: 5
- **Effort**: S
- **Depends on**: `dispatcher-daemon`

First-class retry queue: retry_attempts[issue_id] = {attempt, due_at_ms, timer_handle, error} with min(10s * 2^(attempt-1), max_retry_backoff_ms). Re-checks tracker state before re-dispatch to avoid retry storms on flapping issues.

**Acceptance outcomes**:
- [ ] Backoff schedule is deterministic and bounded
- [ ] Retry re-check prevents dispatch of now-ineligible issues

### agent-runner-port: Agent-runner port with vendor adapters

- **Status**: candidate
- **Priority**: 6
- **Effort**: L
- **Depends on**: `dispatcher-daemon`, `workflow-md-contract`

Vendor-agnostic port: start(workspace, prompt) -> session, stream_events(), cancel(). Normalized event types: turn_started, turn_completed, token_update, rate_limit, approval_request, user_input_requested. Three adapters: Codex (JSON-RPC app-server over stdio), Claude Code CLI, Gemini CLI. user_input_requested is a hard fail.

**Acceptance outcomes**:
- [ ] Same daemon drives all three vendors from the same WORKFLOW.md
- [ ] Normalized event schema covers all Symphony SPEC agent events
- [ ] user_input_requested terminates the session to prevent hangs

### turn-based-continuation: Turn-based session continuation with tracker re-check

- **Status**: candidate
- **Priority**: 7
- **Effort**: M
- **Depends on**: `agent-runner-port`

Within one worker lifetime, stay on the same thread/workspace for up to agent.max_turns, re-checking tracker state between turns. Mid-run transitions to non-eligible states stop the run gracefully and emit a structured run_aborted event.

**Acceptance outcomes**:
- [ ] Same thread/workspace survives across up to max_turns
- [ ] Mid-run state transition preserves workspace and emits run_aborted

### reconciliation-stall-detection: Tracker-state reconciliation and stall detection

- **Status**: candidate
- **Priority**: 8
- **Effort**: M
- **Depends on**: `retry-queue-backoff`, `workspace-manager-hooks`

Each poll tick: stop runs whose issues transitioned to terminal/inactive; detect stalled sessions via inactivity timeout and kill+retry; clean workspaces for terminal issues at startup. Also reconciles against the worktree registry to GC orphans.

**Acceptance outcomes**:
- [ ] Stalled runs killed within stall_timeout_ms
- [ ] Terminal-state workspaces cleaned on next startup
- [ ] Orphan worktrees reconciled against registry

### tracker-graphql-tool: Scoped tracker-GraphQL tool for agents

- **Status**: candidate
- **Priority**: 9
- **Effort**: S
- **Depends on**: `github-tracker-adapter`

Expose a tracker_graphql tool (analog to Symphony's linear_graphql) that lets the agent run scoped GraphQL/REST ops against the active tracker using daemon credentials. One operation per call with an audit-log entry. Primary: GitHub; Linear variant piggybacks on the Linear adapter.

**Acceptance outcomes**:
- [ ] Agent can transition issue state, post comment, link PR without holding raw credentials
- [ ] Every invocation writes one audit-log entry

### token-ratelimit-accounting: Token, rate-limit, and run accounting

- **Status**: candidate
- **Priority**: 10
- **Effort**: S
- **Depends on**: `agent-runner-port`

Central aggregation of Symphony's codex_totals equivalent: per-run and per-daemon input/output/total tokens, runtime seconds, last rate-limit snapshot. Surfaced via structured logs with issue_id, issue_identifier, session_id context keys.

**Acceptance outcomes**:
- [ ] Dashboard can answer tokens-per-issue-per-day without log scraping
- [ ] Rate-limit headroom queryable in real time

### operator-http-status-surface: Operator HTTP status surface

- **Status**: candidate
- **Priority**: 11
- **Effort**: S
- **Depends on**: `token-ratelimit-accounting`

Optional FastAPI sidecar exposing /api/v1/state (running, claimed, retry_attempts, totals, rate limits), /api/v1/<issue_id>, /healthz, /metrics. Sidecar failures must not crash the daemon.

**Acceptance outcomes**:
- [ ] Operator can query live state during long unattended runs
- [ ] Daemon survives sidecar crashes without state loss

### trust-posture-binding: Trust-posture artifact and deployment-profile binding

- **Status**: candidate
- **Priority**: 12
- **Effort**: M
- **Depends on**: `workflow-md-contract`

Require symphony/TRUST_POSTURE.md per deployment declaring approval policy, sandbox mode, network allowlist, coordinator trust level, guardrail posture. Bind to profiles.py and policy_engine.py so posture is enforceable, not just documented.

**Acceptance outcomes**:
- [ ] Daemon refuses to dispatch when posture fields missing or contradictory
- [ ] Posture changes are audited

### coordinator-integration: Daemon and coordinator integration

- **Status**: candidate
- **Priority**: 13
- **Effort**: M
- **Depends on**: `dispatcher-daemon`, `reconciliation-stall-detection`

Wire the daemon into the coordinator as a peer: register via discovery.py, acquire lock-namespace claims through feature_registry.py on dispatch, write to audit on every state transition, respect guardrails and Cedar policies on pre-flight. Must still operate in COORDINATOR_AVAILABLE=false degraded mode.

**Acceptance outcomes**:
- [ ] Daemon runs collide-free with human-triggered /implement-feature
- [ ] End-to-end audit traceability from dispatch to merge
- [ ] Degrades gracefully when coordinator is unreachable

### linear-tracker-adapter: Linear tracker adapter (parallel implementation)

- **Status**: candidate
- **Priority**: 14
- **Effort**: S
- **Depends on**: `github-tracker-adapter`

Linear GraphQL implementation of the tracker port. Demonstrates that the tracker-port abstraction holds and that we are not locked into one tracker.

**Acceptance outcomes**:
- [ ] Swap adapter via tracker.kind in WORKFLOW.md with no daemon code changes
- [ ] Parity with GitHub adapter for the required fetch operations

### harness-readiness-audit: Harness-readiness audit for Symphony-compatibility

- **Status**: candidate
- **Priority**: 15
- **Effort**: S
- **Depends on**: `workflow-md-contract`, `trust-posture-binding`

A /harness-audit (or bug-scrub extension) that scores a target repo against Symphony's implicit prerequisites: hermetic tests, machine-readable build/test/deploy docs, WORKFLOW.md valid, TRUST_POSTURE.md present, openspec initialized, side-effect density from refresh-architecture.

**Acceptance outcomes**:
- [ ] Report flags at least the five prerequisite categories with actionable hints
- [ ] Integrates with existing bug-scrub report format

<!-- GENERATED: end item-details -->

