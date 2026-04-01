# Tasks: remote-control-coordinator

## Phase 1: Event Bus + Outbound Notifications

- [x] **T1.1** Create `agent-coordinator/src/event_bus.py` — generalize `policy_sync.py` into multi-channel `EventBusService` with `on_event(channel, callback)` registration. Include `failed` flag for watchdog health detection. Include payload size check (truncate `context` if NOTIFY payload > 7KB).
- [x] **T1.2** Create database migration for NOTIFY triggers on `approval_queue` (INSERT, UPDATE status), `work_queue` (UPDATE status), `agent_discovery` (INSERT, UPDATE status/heartbeat). Triggers SHALL check `current_setting('app.coordinator_internal')` and skip NOTIFY when `'true'` (prevents self-notification loops).
- [x] **T1.3** Define `CoordinatorEvent` dataclass per the schema in spec.md Definitions section: `event_type`, `channel`, `entity_id` (UUID), `agent_id`, `change_id` (optional), `urgency` (Literal), `summary` (max 200 chars), `context` (dict, optional), `timestamp` (ISO 8601)
- [x] **T1.4** Write tests for `EventBusService` — callback dispatch, reconnection with backoff, multi-channel listening, retry exhaustion behavior, payload truncation
- [x] **T1.5** Create `agent-coordinator/src/notifications/__init__.py` and `base.py` — `NotificationChannel` protocol + `GmailChannelFake` test double
- [x] **T1.6** Create `agent-coordinator/src/notifications/notifier.py` — `NotifierService` with channel registry, urgency classification, parallel dispatch with per-channel error isolation, SMTP retry (exponential backoff, base 2s, max 60s, 3 attempts), event filter per channel via `NOTIFICATION_EVENT_FILTER_{CHANNEL}` env var
- [x] **T1.7** Create `agent-coordinator/src/notifications/gmail.py` — `GmailChannel` outbound (SMTP via `aiosmtplib`, App Password auth), HTML templates, email threading by change-id via `In-Reply-To`/`References` headers
- [x] **T1.8** Create `agent-coordinator/src/notifications/templates.py` — HTML email templates for each event type (approval request, status update, escalation alert, stale agent warning, digest summary)
- [x] **T1.9** Create `agent-coordinator/src/status.py` — notification token generation (8-char via `secrets.token_urlsafe`), storage, validation (atomic `UPDATE WHERE used_at IS NULL`), invalidation
- [x] **T1.10** Create database migration for `notification_tokens` table (token, event_type, entity_id, change_id, created_at, expires_at, used_at)
- [x] **T1.11** Add `aiosmtplib` and `email-validator` to `agent-coordinator/pyproject.toml` dependencies
- [x] **T1.12** Wire event bus and notifier into `coordination_api.py` FastAPI lifespan (start on startup, stop on shutdown)
- [x] **T1.13** Add `POST /notifications/test` and `GET /notifications/status` endpoints to `coordination_api.py`
- [x] **T1.14** Write tests for `NotifierService` — channel dispatch, urgency filtering, disabled mode, per-channel error isolation, SMTP retry, digest batching, event type filtering. Use `GmailChannelFake` test double.
- [x] **T1.15** Write tests for `GmailChannel` outbound — SMTP mock via `aiosmtplib` test mode, template rendering, header generation, threading. Use `freezegun`/`time-machine` for timing tests.

## Phase 2: Inbound Relay + Status Hooks

- [x] **T2.1** Add IMAP IDLE listener to `GmailChannel` — async monitoring via `aioimaplib`, reconnect on IDLE timeout (parameterized, default 29min for Gmail) or disconnect, up to 3 reconnect attempts before emitting `high` urgency event
- [x] **T2.2** Create `agent-coordinator/src/notifications/relay.py` — reply parser: extract token via regex `\[#([A-Za-z0-9]{8})\]` from subject (priority 1) or `In-Reply-To` header (priority 2). Split body by whitespace, strip punctuation from first word, case-insensitive match against command set. Multi-line: first line = command, rest = guidance context.
- [x] **T2.3** Implement reply routing: `approved`/`denied` → `ApprovalService.decide_request()`, `resolved` → `POST /status/report` with `event_type: "gate_check"`, `skip` → `POST /status/report` with `event_type: "phase_skip"`, free-text → `MemoryService.remember()` with tags `["human-feedback", change_id]`
- [x] **T2.4** Implement token lifecycle in relay: validate via atomic `UPDATE WHERE used_at IS NULL`, handle expired/invalid/reused tokens with specific error reply emails. Validate sender case-insensitively against allowlist (no domain wildcards).
- [x] **T2.5** Add `aioimaplib` to `agent-coordinator/pyproject.toml` dependencies (preserve existing `aiosmtplib` and `email-validator` from T1.11)
- [x] **T2.6** Write tests for Gmail relay — parametrized reply parsing (`"approved"`, `"APPROVE!"`, `"yes"`, `"app roved"→None`), token validation, concurrent race (two replies same token), routing to correct service, unauthorized sender rejection. Use `MockIMAPClient` fixture.
- [x] **T2.7** Create `agent-coordinator/scripts/report_status.py` — Claude Code Stop/SubagentStop hook script
- [x] **T2.8** Implement `report_status.py` logic: read `loop-state.json` (handle missing/corrupt JSON gracefully → phase="UNKNOWN"), detect phase change vs `.status-cache.json`, call `POST /status/report` with 5s `httpx` timeout, update heartbeat as side effect, exit 0 in all cases
- [x] **T2.9** Add `POST /status/report` endpoint to `coordination_api.py` — accept status reports, emit `coordinator_status` NOTIFY via direct `pg_notify`. Assumes lifespan wiring from T1.12 is in place.
- [x] **T2.10** Add `report_status` MCP tool to `coordination_mcp.py` for local agents (same fields as HTTP endpoint: `agent_id`, `change_id`, `phase`, `message`, `needs_human`, `metadata`)
- [x] **T2.11** Add `status_fn` callback parameter to `auto_dev_loop.py`'s `run_loop()` — call at phase transitions, escalations, and loop completion. Catch exceptions and timeouts (5s) — log but do NOT crash loop. Include error in next heartbeat.
- [x] **T2.12** Update `.claude/hooks.json` — add Stop and SubagentStop entries for `report_status.py`
- [x] **T2.13** Write tests for `report_status.py` — phase detection, caching, timeout behavior (mock httpx), graceful failure on missing loop-state.json, corrupt JSON, unreachable coordinator
- [x] **T2.14** Write tests for status endpoint — HTTP and MCP paths produce equivalent results, heartbeat side effect verified

## Phase 3: Watchdog + Additional Channels

- [x] **T3.1** Create `agent-coordinator/src/watchdog.py` — async background task with configurable interval (`WATCHDOG_INTERVAL_SECONDS`, default 60, range 10-3600). Inject `time_fn` for deterministic testing.
- [x] **T3.2** Implement stale agent detection: query `agent_discovery` for `last_heartbeat < NOW() - 15min` AND `status = 'active'`, emit notification, call `cleanup_dead_agents()`. Also expire pending approvals from stale agents.
- [x] **T3.3** Implement aging approval detection: query `approval_queue` for pending > 15 min, emit reminder. Debounce via in-memory `last_reminder_at` dict keyed by `approval_id` (30-min interval, resets on restart).
- [x] **T3.4** Implement expiring lock detection: query `file_locks` for TTL within 10 min, warn lock holder
- [x] **T3.5** Implement expired token cleanup: DELETE from `notification_tokens` WHERE `expires_at < NOW()`
- [x] **T3.6** Implement event bus health check: if `event_bus.failed` flag set, emit `high` urgency notification via direct `pg_notify` and attempt event bus restart
- [x] **T3.7** Wire watchdog into `coordination_api.py` lifespan (start on startup, stop on shutdown). Watchdog uses direct `pg_notify` (not event bus listener) to ensure notifications work even if event bus is down.
- [x] **T3.8** Write tests for watchdog — stale detection, approval reminders with debounce verification (using `time-machine`), token cleanup, event bus health check, stale-agent approval expiry
- [x] **T3.9** Create `agent-coordinator/src/notifications/telegram.py` — `TelegramChannel` via Bot API, inline keyboard buttons for approve/deny
- [x] **T3.10** Create `agent-coordinator/src/notifications/webhook.py` — `WebhookChannel` for generic HTTP POST (ntfy, PagerDuty, n8n, Zapier)
- [x] **T3.11** Add digest batching to `NotifierService` — collect low-urgency events, send summary every `NOTIFICATION_DIGEST_INTERVAL_SECONDS` (default 600). Digest contains: event count, per-type summary, 5 most recent summaries. Max batch: 100 events.
- [x] **T3.12** Write tests for Telegram and webhook channels

## Integration

- [x] **T4.1** Merge all package worktrees into feature branch
- [x] **T4.2** Run full coordinator test suite (`pytest -m 'not e2e and not integration'`)
- [x] **T4.3** Run `mypy --strict src/` — verify type checking passes
- [x] **T4.4** Run `ruff check .` — verify linting passes
- [x] **T4.5** Verify `.claude/hooks.json` is valid JSON and scripts are executable
- [x] **T4.6** Manual smoke test: start coordinator, send test notification, verify Gmail delivery
- [x] **T4.7** Update `agent-coordinator/CLAUDE.md` with new env vars and tool descriptions

## Migration Notes

All tasks implemented via PR #50 (merged 2026-03-31). Review findings #1-#15 addressed in commit 48d1b06.
Migration 015 table name bug fixed in commit 07ce6e6. No open tasks remain.
Rate limiting for POST /status/report (#14) intentionally deferred to reverse proxy layer.
