# Design: remote-control-coordinator

## Context

The Agent Coordinator provides multi-agent coordination via MCP (local agents) and HTTP API (cloud agents), backed by PostgreSQL. It has an approval queue (`src/approval.py`) with no notification mechanism — humans must poll. It has a push-based LISTEN/NOTIFY pattern in `src/policy_sync.py` but only for policy cache invalidation on a single channel. Agents report presence via heartbeat and discovery, but there is no proactive alerting when agents go stale, approvals age, or the auto-dev-loop escalates.

The system must remain agent-agnostic: Claude Code gets deeper integration via hooks, but Codex and Gemini agents must have feature parity through the HTTP API. PostgreSQL is the only database dependency — no Supabase-specific features (Realtime, PostgREST auth, etc.).

## Goals / Non-Goals

### Goals

- **G1**: Proactive push notifications for coordinator events (approvals, escalations, stale agents, task completions) via pluggable channels
- **G2**: Bidirectional Gmail channel — send notifications, receive replies that route to coordinator API endpoints (approve, deny, inject guidance)
- **G3**: Claude Code hook integration for heartbeats and auto-dev-loop status reporting, with HTTP API fallback for Codex/Gemini
- **G4**: Watchdog service for periodic health checks (stale agents, aging approvals, expiring locks)
- **G5**: Agent-agnostic design — all features accessible via HTTP API; hooks are optional enrichment

### Non-Goals

- Mobile app or custom web dashboard (use existing tools — Gmail, Telegram, etc.)
- Real-time streaming UI (that's an observability concern, covered by OpenTelemetry)
- Replacing Claude Code Channels or Remote Control — those are session-scoped; this is coordination-scoped
- WhatsApp integration (no stable bot API for automated messaging)
- Auto-executing arbitrary commands from email replies (security boundary — only route to existing coordinator endpoints)

## Decisions

### D1: Generalize LISTEN/NOTIFY into an Event Bus

**Decision**: Extract the `PgListenNotifyPolicySyncService` pattern from `policy_sync.py` into a general-purpose `EventBusService` that listens on multiple PostgreSQL NOTIFY channels and dispatches to registered callbacks.

**Rationale**: The existing pattern already handles reconnection with exponential backoff, callback registration, and safe error handling. Generalizing it avoids duplicating this logic per-channel. Database triggers on `approval_queue`, `work_queue`, and `agent_discovery` tables emit NOTIFY events — pure PostgreSQL, no Supabase dependency.

**Channels**:
- `coordinator_approval` — approval submitted, decided, expired
- `coordinator_task` — task claimed, completed, failed
- `coordinator_agent` — agent registered, stale, disconnected
- `coordinator_status` — phase transitions, escalations from auto-dev-loop
- `coordinator_guardrail` — destructive operation blocked

### D2: Channel Plugin Interface

**Decision**: Define a `NotificationChannel` Protocol with `send()`, `test()`, `supports_reply()` methods. The `NotifierService` maintains a registry of enabled channels and dispatches events to all of them in parallel.

**Rationale**: Same pattern as Claude-Code-Remote's Notifier class, but async and Python-native. Adding new channels (Telegram, Slack, ntfy, PagerDuty) requires only implementing the Protocol — no changes to the core notifier or event bus.

```python
class NotificationChannel(Protocol):
    """Plugin interface for notification delivery channels."""
    channel_id: str

    async def send(self, event: CoordinatorEvent) -> bool:
        """Send a notification. Returns True on success."""
        ...

    async def test(self) -> bool:
        """Test channel connectivity."""
        ...

    def supports_reply(self) -> bool:
        """Whether this channel can receive and relay responses."""
        ...
```

### D3: Gmail as Primary Bidirectional Channel

**Decision**: Implement Gmail via `aiosmtplib` (outbound) and `aioimaplib` (inbound IMAP IDLE). Replies are parsed and routed to coordinator API endpoints. Use App Passwords or OAuth2 for authentication.

**Rationale**: Gmail supports IMAP IDLE for near-real-time push (1-5s latency). Email provides threading by change-id, rich HTML bodies, and works from any device. IMAP IDLE has a 29-minute timeout (Gmail-specific) — reconnect and re-IDLE. This matches Claude-Code-Remote's proven IMAP approach.

**Reply parsing**: Single-word commands (`approved`, `denied`, `resolved`, `skip`) for common actions, free-text for guidance injection. Token extracted from subject line pattern `[#TOKEN]` or `In-Reply-To` header matching.

### D4: Notification Tokens (One-Time, Short-Lived)

**Decision**: Each notification that requires a response includes an 8-character alphanumeric token with configurable TTL (default 1 hour). Tokens are stored in a `notification_tokens` table, bound to a specific event (approval_id, change_id, event_type). Single-use — invalidated after first response.

**Rationale**: This prevents replay attacks from forwarded emails. Short TTL limits exposure. Sender allowlist provides the second factor. The coordinator's existing `session_permission_grants` table could be reused, but a dedicated table is cleaner for token lifecycle management (creation, validation, invalidation, expiration).

### D5: Two-Path Status Reporting (Hooks + HTTP API)

**Decision**: Claude Code agents report status via a `Stop` hook (`report_status.py`) that reads `loop-state.json` and calls the coordinator. Codex/Gemini agents call `POST /status/report` directly. Both paths emit the same `coordinator_status` NOTIFY event.

**Rationale**: The `Stop` hook fires after every Claude Code agent turn — it's a natural heartbeat that requires no agent-side code changes. For Codex/Gemini, the HTTP endpoint provides equivalent functionality. The auto-dev-loop's `status_fn` callback uses whichever path is available.

### D6: Watchdog as Async Loop in API Server

**Decision**: Run the watchdog as an `asyncio` background task within the existing `coordination_api.py` FastAPI server, not as a separate daemon process.

**Rationale**: Avoids a new deployment artifact. FastAPI's `lifespan` context manager provides clean startup/shutdown. The watchdog runs periodic queries (every 60s) against existing tables — no schema changes needed. If the API server restarts, the watchdog restarts with it.

### D7: Event Urgency Classification

**Decision**: Events have an `urgency` field: `low` (batch into digest), `medium` (send within 1 minute), `high` (send immediately). The notifier respects urgency per channel — Gmail batches low-urgency events into periodic digests, but sends high-urgency events immediately.

**Rationale**: Prevents notification fatigue. Phase transitions are interesting but not urgent. Escalations, approval requests, and stale agents need immediate attention.

## Alternatives Considered

### A1: Use Supabase Realtime Instead of LISTEN/NOTIFY

**Rejected**: Supabase Realtime requires the Supabase client library and specific publication setup. The project is moving toward plain PostgreSQL compatibility. LISTEN/NOTIFY is standard PostgreSQL, works with asyncpg directly, and the pattern is already proven in `policy_sync.py`.

### A2: Webhook-Only (No IMAP)

**Rejected**: Webhook receivers require a publicly accessible endpoint. The coordinator may run on a developer machine without a public IP. IMAP IDLE works behind NAT/firewalls because it's an outbound connection. Webhooks can be added later as an additional channel for cloud deployments.

### A3: Claude Code Channels as the Notification Layer

**Rejected**: Channels is session-scoped and Claude Code-specific. The coordinator needs to notify about database events that aren't tied to any session (e.g., "no agent has picked up task X for 30 minutes"). Also, Codex/Gemini can't use Channels.

### A4: Separate Notification Microservice

**Rejected**: Over-engineering for current scale. The event bus listener and notifier are lightweight async tasks. Running them in the existing API server process keeps deployment simple. Can extract later if needed.

### A5: SMS/Voice for Urgent Notifications

**Deferred**: Twilio/SMS adds cost and API dependency. Gmail push + Telegram covers urgency well enough. Can add later as another channel plugin.

## Risks / Trade-offs

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Gmail App Password / OAuth2 credential management | Medium | Medium | Document setup clearly; support both auth methods; credentials via env vars, not stored in DB |
| IMAP IDLE connection drops silently | Low | Medium | Reconnect with exponential backoff (same pattern as policy_sync.py); watchdog self-monitors IMAP health |
| Notification spam from chatty events | Medium | High | Urgency classification + digest batching for low-urgency events; configurable event type filter |
| Reply parsing ambiguity | Low | Medium | Conservative parsing — only act on exact keyword matches; free-text goes to guidance injection, not approvals |
| Email delivery delays (Gmail throttling) | Low | Low | Use dedicated sender address; respect Gmail SMTP rate limits (500/day for App Password) |
| Hook script latency blocks Claude Code turn | Medium | Low | `report_status.py` is fire-and-forget with 5s timeout; failures are logged, not blocking |

## Migration Plan

### Phase 1: Event Bus + Outbound Notifications

1. Add `event_bus.py` (generalized LISTEN/NOTIFY listener)
2. Add database triggers on `approval_queue`, `work_queue`, `agent_discovery`
3. Add `notifications/` package with `NotifierService` and `GmailChannel` (outbound SMTP only)
4. Add `POST /notifications/test` endpoint for channel verification
5. Wire event bus → notifier in `coordination_api.py` lifespan

### Phase 2: Inbound Relay + Status Hooks

1. Add IMAP IDLE listener to `GmailChannel` for reply processing
2. Add `notification_tokens` table and token lifecycle management
3. Add `report_status.py` hook script and `POST /status/report` endpoint
4. Add `status_fn` callback to auto-dev-loop's `run_loop()`
5. Update `.claude/hooks.json` with Stop/SubagentStop hooks

### Phase 3: Watchdog + Additional Channels

1. Add `watchdog.py` as asyncio background task
2. Add `TelegramChannel` plugin
3. Add `WebhookChannel` plugin (generic HTTP POST for ntfy, PagerDuty, n8n)
4. Add digest batching for low-urgency events

### Rollback

Each phase is independently deployable. The event bus and notifier are opt-in via `NOTIFICATION_CHANNELS` env var (default: empty = disabled). Removing the env var disables all notifications without code changes. Database triggers are additive (NOTIFY on INSERT/UPDATE) and don't affect existing functionality.
