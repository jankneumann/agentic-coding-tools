# Change: remote-control-coordinator

## Why

The Agent Coordinator has a sophisticated backend for multi-agent coordination (locks, work queue, approvals, guardrails, memory) but no way to proactively reach humans. The approval queue requires polling. Stale agents go unnoticed until heartbeat TTL expires. The auto-dev-loop's ESCALATE phase prints to a terminal that nobody may be watching. When agents run for hours on complex features, the human operator needs push notifications for critical events and the ability to respond remotely — approve operations, unblock escalations, or inject guidance — without opening a terminal.

Claude-Code-Remote (JessyTsui) demonstrates that email and messaging relay works reliably for single-session control. Claude Code's official Channels feature (March 2026) adds Telegram/Discord/iMessage plugins for individual sessions. Neither addresses multi-agent coordination: knowing which of several agents needs attention, routing approvals to the right decision endpoint, or correlating notifications with change-ids. The coordinator is the natural hub for this.

## What Changes

- Add a **generalized event bus** by extending PostgreSQL LISTEN/NOTIFY beyond the existing `policy_changed` channel to cover task lifecycle, approvals, agent health, and guardrail events
- Add a **pluggable Notifier service** with a channel abstraction (Gmail, Telegram, webhook) that subscribes to the event bus and dispatches notifications
- Add a **Gmail channel** with SMTP outbound and IMAP IDLE inbound for reply-to-approve and reply-to-unblock workflows
- Add a **`report_status.py` Claude Code hook** (Stop/SubagentStop) that updates heartbeats and reports phase transitions from the auto-dev-loop — with an equivalent HTTP API endpoint for Codex/Gemini agents
- Add a **watchdog loop** that monitors stale agents, aging approval requests, and approaching lock expirations, triggering notifications when thresholds are crossed

## Impact

- Affected specs: `agent-coordinator` (new event bus, notifier, status endpoint)
- New code:
  - `agent-coordinator/src/event_bus.py` — generalized LISTEN/NOTIFY listener (extends `policy_sync.py` pattern)
  - `agent-coordinator/src/notifications/` — Notifier service, channel plugins (Gmail, Telegram, webhook)
  - `agent-coordinator/src/status.py` — status reporting service + notification token management
  - `agent-coordinator/src/watchdog.py` — periodic health monitoring loop
- Modified code:
  - `agent-coordinator/src/coordination_api.py` — new `POST /status/report` and `POST /notifications/test` endpoints
  - `agent-coordinator/src/coordination_mcp.py` — new `report_status` MCP tool
  - `.claude/hooks.json` — add Stop and SubagentStop hooks
- New scripts:
  - `agent-coordinator/scripts/report_status.py` — Claude Code hook script
- New migrations:
  - `notification_tokens` table (short-lived tokens for reply-to-approve)
  - NOTIFY triggers on `approval_queue`, `work_queue`, `agent_discovery` tables
- New config env vars: `NOTIFICATION_CHANNELS`, `SMTP_*`, `IMAP_*`, `NOTIFICATION_ALLOWED_SENDERS`, `TELEGRAM_BOT_TOKEN`, `WEBHOOK_URL`
- Skills touched: `auto-dev-loop` (add `status_fn` callback alongside existing `memory_fn`/`handoff_fn`)

## Analysis: Notification Patterns Considered

### Claude-Code-Remote (JessyTsui)

| Aspect | Their Approach | Our Adaptation |
|--------|---------------|----------------|
| **Trigger** | Claude Code hooks (Stop, SubagentStop) | Same hooks + coordinator event bus (works for all agents) |
| **Outbound** | Email (SMTP), Telegram, LINE, Desktop | Email (SMTP), Telegram, generic webhook |
| **Inbound** | IMAP polling + Telegram webhook + LINE webhook | IMAP IDLE (near-real-time) + Telegram webhook |
| **Relay** | Inject keystrokes into terminal (PTY/tmux) | Route to coordinator API endpoints (approve, inject guidance) |
| **Session binding** | 8-char token in subject line, 24h TTL | Same pattern, shorter TTL (1h default), bound to specific event |
| **Security** | Sender whitelist, token expiration | Same + coordinator's existing trust/policy layers |

### Claude Code Official Features

| Feature | Relationship |
|---------|-------------|
| **Channels** (Telegram/Discord/iMessage) | Session-scoped; doesn't coordinate across agents. Coordinator notifications are complementary — they cover multi-agent events that no single session sees |
| **Remote Control** | Drives a single session from claude.ai/mobile. Coordinator can register remote-controllable sessions in discovery for cross-agent visibility |
| **Teleport** | Moves web session to local. Coordinator handoff documents can include teleport metadata for seamless continuation |
| **Agent Teams** (experimental) | Peer-to-peer messaging + file locking. Coordinator is the "enterprise upgrade" — richer policies, memory, audit. Notification layer makes the coordinator's approval queue actually usable |

### Why NOT Use Claude Code Channels Directly

1. **Agent-agnostic requirement**: Channels is Claude Code-specific. Codex and Gemini agents can't use it. The coordinator notification system works for all agents via the HTTP API.
2. **Event source is the database, not a session**: The coordinator needs to notify on database events (approval pending, agent stale, lock contention) that aren't tied to any single agent session.
3. **Reply routing**: Channels delivers messages into a session. We need replies routed to coordinator API endpoints (approve/deny/inject guidance), not into a terminal.
4. **Complementary**: Teams using Claude Code can enable Channels for session-level alerts AND coordinator notifications for multi-agent orchestration events. They serve different purposes.
