# Proposal: Agent State Observatory — Global Visualization, Session Management, and Cross-Repo Learning

**Status**: Roadmap input (not yet an approved change)
**Author**: Operator + Claude (Opus 4.6)
**Date**: 2026-04-14
**Branch**: `claude/explore-agent-visualization-15cLG`

## Summary

Build a progressively layered "agent state observatory" that surfaces what multi-agent sessions are doing, lets the operator manage and fork conversations, shares knowledge across repos, integrates with the ghostty terminal workflow, and surfaces historical analytics. The proposal is scoped as a multi-phase roadmap rather than a single change — each capability below should become its own OpenSpec change with explicit dependencies.

## Operator Context

The operator runs **one ghostty window per repo/working directory**, with multiple tabs inside each window for agents and shells. The three primary repos in play — a coding repo (this one), a knowledge-management repo, and a personal-assistant repo — increasingly overlap in patterns, prompts, and learnings. No single view shows state across repos today; tab-hopping does not scale as parallel agents and repos multiply.

## Priority Order

1. **Observability** — see everything, live, across all active agents and repos.
2. **Session management** — conversation browser, forks (combined with "fork-worktrees"), replay.
3. **Cross-repo learning and sharing** — patterns, prompts, and archived knowledge flow between repos.
4. **Terminal-workflow integration** — ghostty-native surfaces, status lines, notifications.
5. **Historical analytics** — per-agent-type performance, change post-mortems, cost attribution.

The roadmap MUST respect this ordering: higher-priority phases block lower-priority ones unless a lower-priority item has zero dependency on higher phases.

## Architectural Touchpoints

The coordinator (`agent-coordinator/src/`) already exposes ~40 HTTP routes covering locks, work queue, discovery, audit, handoffs, approvals, guardrails, merge trains, and OTEL telemetry. The per-repo worktree registry (`.git-worktrees/.registry.json`) is file-local. Session logs and handoffs already produce durable artifacts per change. The OpenSpec archive (`docs/factory-intelligence/archive-index.json`, `exemplars.json`) captures patterns from completed changes. **Most roadmap items are render-and-aggregate work on top of these existing substrates** — not net-new backends.

---

## Phase 1 — Observability Foundations

The highest priority and prerequisite for everything else. Without a live data feed and aggregated state, every downstream UI would have to poll or re-implement its own plumbing.

### Capability: Agent State Event Stream

The coordinator SHALL expose a Server-Sent Events endpoint (`/events/stream`) that multiplexes agent registration, heartbeat, lock acquire/release, work claim/complete, approval-pending, guardrail-block, and merge-train-progress events. Consumers subscribe once and receive a live feed with at-most-once semantics and replay-from-cursor support.

**Acceptance outcomes**:
- A consumer can subscribe to the stream and receive a typed event within 1 second of the originating state change in the coordinator.
- Events carry enough identity (agent_id, change_id, repo) to be filtered client-side without follow-up API calls.
- Reconnecting with a `Last-Event-ID` header resumes the stream without gaps or duplicates within a 5-minute window.

### Capability: Cross-Repo Worktree Registry Aggregator

Each repo's `worktree.py` SHALL report registry deltas to the coordinator on heartbeat, producing a central index queryable as "all active worktrees across all repos." This replaces the file-local-only view.

**Acceptance outcomes**:
- A new `GET /worktrees` endpoint returns all active worktrees across all reporting repos with owner, branch, heartbeat age, pin status, and repo identifier.
- Stale entries (heartbeat older than threshold) are flagged but retained for audit.
- A repo that has never reported is not required to participate; the feature degrades gracefully.

### Capability: Agent State TUI

A Textual-based terminal UI SHALL subscribe to the event stream and render a global dashboard with panels for active agents, current locks, pending approvals, work queue depth, and cross-repo worktrees. It runs in its own ghostty tab and requires no packaging beyond `uv run`.

**Acceptance outcomes**:
- Launching `uv run skill agent-observatory` in any repo displays a live global view updating within 1 second of state changes.
- The UI works over the same coordinator URL regardless of which repo it was launched from.
- Every panel has a keyboard action to drill into details (show diff, show audit trail, show lock contenders).

### Capability: Active Operator Controls

The TUI and any future dashboard SHALL surface write-side coordinator actions: approve/reject approvals, force-release stale locks, pause/resume agents, and reorder the work queue. Each action maps to an existing coordinator endpoint.

**Acceptance outcomes**:
- An operator can approve a pending approval from the UI without dropping to CLI.
- A stale lock can be force-released with a confirmation prompt and audit-logged identity.
- Pausing an agent halts its next `/work/claim` cycle until resumed.

---

## Phase 2 — Session Management

Builds directly on Phase 1's data feed but introduces a new first-class object: the conversation. Canopy-inspired but extended to work with worktrees and multi-agent orchestration.

### Capability: Conversation Capture and Indexing

Every agent session SHALL emit structured conversation records (user turns, assistant turns, tool calls, tool results, and phase markers) to a durable store indexed by repo, branch, change_id, and timestamp. Existing session-log artifacts provide the seed; new instrumentation covers live sessions.

**Acceptance outcomes**:
- A session that ran 30 days ago can be retrieved by change_id and replayed turn-by-turn.
- Conversations are searchable by free-text content and structured filters (agent_type, tool, time range).
- Token counts and model identifiers are captured per turn for later cost attribution.

### Capability: Conversation Browser

A UI surface SHALL list all captured conversations with title, branch, status, last activity, and preview, with full-text search. Clicking a conversation opens a turn-by-turn viewer.

**Acceptance outcomes**:
- The browser lists the 1000 most-recent conversations with pagination and filters.
- Free-text search returns matches ranked by recency and relevance within 2 seconds over a 10k-conversation store.
- Each conversation links to its OpenSpec change and PR when applicable.

### Capability: Fork-Worktree Conversations

An operator SHALL be able to fork any conversation at turn N. Forking creates a new conversation branch AND a new git worktree seeded from the original worktree's commit, so both the conversation state and the code state are forked in lockstep. The new conversation can then proceed with an edited prompt or different agent type.

**Acceptance outcomes**:
- Forking conversation C at turn N produces conversation C' with turns 1..N copied and a new worktree at `.git-worktrees/<change-id>/fork-<n>/` checked out from the same commit the original session was on at turn N.
- Both forks appear in the conversation browser with a visible parent/child relationship.
- Killing a fork tears down both the conversation and the worktree cleanly.

### Capability: Conversation Replay

The UI SHALL step through a completed or in-progress conversation showing each turn with full tool-call arguments and results, optionally replaying with a different agent or model to compare outcomes.

**Acceptance outcomes**:
- Stepping through a conversation renders each turn with identical content to the original session.
- Replay mode reconstructs prompts and tools from audit logs and can re-dispatch to a different agent type with the original starting context.
- Diff-view between original and replay shows token-level changes in assistant output.

---

## Phase 3 — Cross-Repo Learning

Grows out of Phase 2's conversation store. Where Phase 2 makes conversations first-class within a single repo, Phase 3 makes patterns and knowledge first-class across the operator's portfolio (coding, knowledge-management, personal-assistant).

### Capability: Shared Archive Index

The existing `docs/factory-intelligence/archive-index.json` and `exemplars.json` SHALL be extended to a cross-repo index. A shared coordinator endpoint aggregates archive entries from every participating repo, allowing any repo to query "show me changes in any repo that touched capability X."

**Acceptance outcomes**:
- A query for capability "skill-workflow" returns exemplars from all three repos, each labeled with its repo identifier.
- Each shared exemplar links back to its source PR and change directory.
- A repo can opt out of sharing specific changes via a metadata flag.

### Capability: Cross-Repo Pattern Mining

A periodic job SHALL analyze the shared conversation store and archive index to surface recurring patterns — prompt templates that keep appearing, tool-call sequences that indicate the same sub-task, failure patterns that cross repos. Results feed into OpenSpec proposal candidates (ties to `harness-engineering-features` Feature 4).

**Acceptance outcomes**:
- The job produces a weekly `cross-repo-patterns.json` artifact ranked by frequency and spread (how many repos exhibit the pattern).
- Each pattern has suggested "promote to shared skill" or "add guardrail" next actions.
- Patterns with strong signal auto-generate draft OpenSpec proposals for operator review.

### Capability: Shared Prompt / Skill Library

Skills, prompts, and guardrails SHALL be pullable across repos via the existing `skills/install.sh` sync mechanism extended with a "subscribe to" upstream repo. Each repo pins a specific version and can cherry-pick which skills to import.

**Acceptance outcomes**:
- Repo B can subscribe to repo A's skills directory and pull a named skill version.
- Pinned versions are captured in a lockfile and diffable on update.
- Local edits in the subscribing repo are preserved across upstream updates (three-way merge).

---

## Phase 4 — Terminal Workflow Integration

Not a prerequisite for higher-priority phases but substantially improves daily ergonomics once Phases 1-3 are in place.

### Capability: Ghostty Quick-Terminal TUI Binding

A keybind SHALL pop up the agent state TUI in ghostty's quick-terminal overlay, giving ambient access from any ghostty window without dedicating a tab.

**Acceptance outcomes**:
- Pressing the configured keybind in any ghostty window opens the TUI as an overlay.
- Dismissing the overlay preserves the TUI process for fast re-open.
- The overlay shows a compact mode; expanding promotes it to a full tab.

### Capability: Status Line Integration

Shell prompts in agent tabs SHALL optionally display coordinator state inline: current lock holdings, queue depth, pending approvals for the agent's change_id.

**Acceptance outcomes**:
- A Zsh/Bash prompt module renders coordinator state with a single environment toggle.
- Prompt updates are throttled to avoid flicker on tight loops.
- Disabling the module has zero residual overhead.

### Capability: Desktop Notifications

A lightweight notification bridge SHALL emit OS-native notifications for approval-pending, agent-blocked, CI-failed, and lock-contention events, gated by operator-configurable rules.

**Acceptance outcomes**:
- Approval pending for any repo produces a notification within 2 seconds.
- Notification rules can be configured per event type and per repo.
- Clicking a notification focuses the relevant ghostty window/tab where supported.

---

## Phase 5 — Historical Analytics

Lowest-priority phase. Builds on Phase 2's conversation store and the existing OTEL/audit infrastructure.

### Capability: Per-Agent-Type Performance Dashboard

Grafana or a coordinator-hosted analytics view SHALL show per-agent-type metrics: pass rate, iterations-to-merge, time-to-PR, review-consensus iterations, capability-gap frequency.

**Acceptance outcomes**:
- Comparing claude-code vs codex vs gemini shows normalized metrics over a selectable time window.
- Drill-down links to specific changes/PRs that contributed to each metric.
- Metrics refresh within 5 minutes of the underlying audit event.

### Capability: Change Post-Mortem Reconstructor

Given any archived change, the system SHALL reconstruct and render its lifecycle: DAG shape, worktrees used, review iterations, rework cycles, time in each phase.

**Acceptance outcomes**:
- Any change in the archive index produces a post-mortem view within 10 seconds.
- Post-mortem data is exported as JSON for feeding back into exemplar learning.
- Anomalies (e.g., unusually long review phase) are flagged.

### Capability: Cost Attribution

Langfuse-captured token usage SHALL be attributed to changes, agents, and repos, producing a weekly spend breakdown.

**Acceptance outcomes**:
- Weekly report shows spend per repo, per agent-type, per change.
- Outlier detection highlights changes exceeding typical spend.
- Cost data is queryable via an endpoint consumable by the dashboard.

---

---

## Future Ideas (Out of Scope for This Roadmap)

The following ideas surfaced during exploration but do not fall under the five prioritized categories above. They are parked here intentionally so the roadmap stays focused and the operator's priority ordering is respected. Any of them can be promoted into a future roadmap cycle if the underlying pain becomes acute.

### Desktop/Native Shells

- **Tauri desktop shell** wrapping the web dashboard with system tray, native notifications, and a persistent window decoupled from browser tab management.
- **Native Swift macOS menu-bar status item** with a compact indicator and popover for passive glances.

*Rationale for deferral*: Both introduce toolchains (Rust+JS or Swift/Xcode) that nothing else in these repos uses. The TUI + shell keybind integration (Phase 4) is expected to cover most of the "passive glance" need without a new stack. Revisit only if the web dashboard and TUI together prove insufficient.

### Collaborative / Multi-Human Features

- **Operator presence**: show a second human's cursor/context when reviewing or approving, for remote pairing.
- **Shared annotations**: comment on an agent's work-in-progress from the dashboard, posted via handoffs.
- **Approval delegation**: route approvals of type X to user Y with fallback rules.

*Rationale for deferral*: Solo operator today. These become relevant only when the team expands beyond one human.

### Experimental / Speculative

- **Live "what is the agent thinking right now?" view**: tail the assistant's current token stream across every active session with syntax-aware highlighting for tool calls, reasoning, and diffs. Essentially `top(1)` for agent cognition.
- **Agent "twitch stream" feed**: a vertical feed of recent tool calls across all agents, filterable — surprisingly useful for spotting loops and bad patterns.
- **Simulation mode**: replay a past change but with a different agent, prompt, or model, and compare outcomes quantitatively. Requires hermetic agent sandboxing.
- **Auto-generated OpenSpec proposals from capability-gap patterns**: take the output of Phase 3's pattern mining and automatically draft proposal skeletons for operator triage. Overlaps with `harness-engineering-features` Feature 4.

*Rationale for deferral*: High upside but either require new instrumentation beyond the current coordinator's capture scope (token streams, hermetic replay) or depend on Phase 3's pattern mining being mature first. Good candidates for a "v2" roadmap once Phases 1-3 are in production.

### Alternative Form Factors Considered

- **Grafana-only dashboards over existing OTEL**: strictly a subset of Phase 5. Parked as an implementation option for the "Per-Agent-Type Performance Dashboard" capability rather than a standalone roadmap item.
- **Web-only dashboard as the primary UI**: considered as a replacement for the TUI but rejected for Phase 1 because the TUI fits the ghostty-window-per-repo workflow natively and avoids browser tab management overhead. The web dashboard remains a natural follow-up in a later cycle once the data model is validated.
- **Coordinator-integrated approval/control web UI** (without full dashboard): considered as a minimal "just the buttons" surface. Rejected because the operator-controls capability in Phase 1 already delivers this via the TUI, and standing up a separate web surface for buttons alone is poor leverage.

---

## Constraints

- **No new language stacks without justification**: Python/Textual for TUI, FastAPI static for web UI; defer Rust/Swift/Electron until data model is validated by at least one lightweight UI.
- **Reversibility**: Every phase MUST be shippable and useful without the next phase landing.
- **Reuse over new infrastructure**: extend the coordinator, audit, telemetry, and event bus rather than forking them.
- **Priority ordering is load-bearing**: Observability precedes session management precedes cross-repo learning precedes terminal ergonomics precedes analytics. Any dependency that inverts this ordering MUST be called out explicitly.
- **Session management must not compromise worktree hygiene**: fork-worktree conversations must interact cleanly with the existing worktree registry, pin, and GC semantics.
- **Cross-repo features require opt-in**: a repo is never enrolled in sharing without an explicit configuration step.
- **Degradation without coordinator**: TUI and CLI tools MUST continue to work in a reduced-function mode when the coordinator is unreachable, using local registry and filesystem artifacts.
