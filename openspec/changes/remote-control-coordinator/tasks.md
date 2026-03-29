# Tasks: remote-control-coordinator

## Phase 1: Event Bus + Outbound Notifications

- [ ] **T1.1** Create `agent-coordinator/src/event_bus.py` — generalize `policy_sync.py` into multi-channel `EventBusService` with `on_event(channel, callback)` registration
- [ ] **T1.2** Create database migration for NOTIFY triggers on `approval_queue` (INSERT, UPDATE status), `work_queue` (UPDATE status), `agent_discovery` (INSERT, UPDATE status/heartbeat)
- [ ] **T1.3** Define `CoordinatorEvent` dataclass with fields: `event_type`, `channel`, `entity_id`, `agent_id`, `change_id`, `urgency`, `summary`, `context`, `timestamp`
- [ ] **T1.4** Write tests for `EventBusService` — callback dispatch, reconnection, multi-channel listening
- [ ] **T1.5** Create `agent-coordinator/src/notifications/__init__.py` and `base.py` — `NotificationChannel` protocol
- [ ] **T1.6** Create `agent-coordinator/src/notifications/notifier.py` — `NotifierService` with channel registry, urgency classification, parallel dispatch
- [ ] **T1.7** Create `agent-coordinator/src/notifications/gmail.py` — `GmailChannel` outbound (SMTP via `aiosmtplib`), HTML templates, email threading by change-id
- [ ] **T1.8** Create `agent-coordinator/src/notifications/templates.py` — HTML email templates for each event type (approval request, status update, escalation alert, stale agent warning)
- [ ] **T1.9** Create `agent-coordinator/src/status.py` — notification token generation, storage, validation, invalidation
- [ ] **T1.10** Create database migration for `notification_tokens` table (token, event_type, entity_id, change_id, created_at, expires_at, used_at)
- [ ] **T1.11** Add `aiosmtplib` and `email-validator` to `agent-coordinator/pyproject.toml` dependencies
- [ ] **T1.12** Wire event bus and notifier into `coordination_api.py` FastAPI lifespan
- [ ] **T1.13** Add `POST /notifications/test` and `GET /notifications/status` endpoints to `coordination_api.py`
- [ ] **T1.14** Write tests for `NotifierService` — channel dispatch, urgency filtering, disabled mode
- [ ] **T1.15** Write tests for `GmailChannel` outbound — SMTP mock, template rendering, header generation

## Phase 2: Inbound Relay + Status Hooks

- [ ] **T2.1** Add IMAP IDLE listener to `GmailChannel` — async monitoring via `aioimaplib`, reconnect on timeout/disconnect
- [ ] **T2.2** Create `agent-coordinator/src/notifications/relay.py` — reply parser (token extraction, command recognition, sender validation)
- [ ] **T2.3** Implement reply routing: approval decisions → `ApprovalService.decide_request()`, guidance → `MemoryService.remember()`, gate checks → status update
- [ ] **T2.4** Implement token lifecycle in relay: validate, invalidate on use, handle expired/invalid tokens with error reply emails
- [ ] **T2.5** Add `aioimaplib` to `agent-coordinator/pyproject.toml` dependencies
- [ ] **T2.6** Write tests for Gmail relay — reply parsing, token validation, routing (mocked IMAP)
- [ ] **T2.7** Create `agent-coordinator/scripts/report_status.py` — Claude Code Stop/SubagentStop hook script
- [ ] **T2.8** Implement `report_status.py` logic: read `loop-state.json`, detect phase change vs cached state, call `POST /status/report`, update heartbeat, 5s timeout
- [ ] **T2.9** Add `POST /status/report` endpoint to `coordination_api.py` — accept status reports, emit `coordinator_status` NOTIFY
- [ ] **T2.10** Add `report_status` MCP tool to `coordination_mcp.py` for local agents
- [ ] **T2.11** Add `status_fn` callback parameter to `auto_dev_loop.py`'s `run_loop()` — call at phase transitions, escalations, and loop completion
- [ ] **T2.12** Update `.claude/hooks.json` — add Stop and SubagentStop entries for `report_status.py`
- [ ] **T2.13** Write tests for `report_status.py` — phase detection, caching, timeout behavior, graceful failure
- [ ] **T2.14** Write tests for status endpoint — HTTP and MCP paths, heartbeat side effect

## Phase 3: Watchdog + Additional Channels

- [ ] **T3.1** Create `agent-coordinator/src/watchdog.py` — async background task with configurable interval
- [ ] **T3.2** Implement stale agent detection: query `agent_discovery` for `last_heartbeat < NOW() - 15min`, emit notification, call `cleanup_dead_agents()`
- [ ] **T3.3** Implement aging approval detection: query `approval_queue` for pending > 15 min, emit reminder (debounced to once per 30 min per approval)
- [ ] **T3.4** Implement expiring lock detection: query `file_locks` for TTL within 10 min, warn lock holder
- [ ] **T3.5** Implement expired token cleanup: DELETE from `notification_tokens` WHERE `expires_at < NOW()`
- [ ] **T3.6** Wire watchdog into `coordination_api.py` lifespan (start on startup, stop on shutdown)
- [ ] **T3.7** Write tests for watchdog — stale detection, approval reminders, debouncing, token cleanup
- [ ] **T3.8** Create `agent-coordinator/src/notifications/telegram.py` — `TelegramChannel` via Bot API, inline keyboard buttons for approve/deny
- [ ] **T3.9** Create `agent-coordinator/src/notifications/webhook.py` — `WebhookChannel` for generic HTTP POST (ntfy, PagerDuty, n8n, Zapier)
- [ ] **T3.10** Add digest batching to `NotifierService` — collect low-urgency events, send summary every N minutes (configurable)
- [ ] **T3.11** Write tests for Telegram and webhook channels

## Integration

- [ ] **T4.1** Merge all package worktrees into feature branch
- [ ] **T4.2** Run full coordinator test suite (`pytest -m 'not e2e and not integration'`)
- [ ] **T4.3** Run `mypy --strict src/` — verify type checking passes
- [ ] **T4.4** Run `ruff check .` — verify linting passes
- [ ] **T4.5** Verify `.claude/hooks.json` is valid JSON and scripts are executable
- [ ] **T4.6** Manual smoke test: start coordinator, send test notification, verify Gmail delivery
- [ ] **T4.7** Update `agent-coordinator/CLAUDE.md` with new env vars and tool descriptions
