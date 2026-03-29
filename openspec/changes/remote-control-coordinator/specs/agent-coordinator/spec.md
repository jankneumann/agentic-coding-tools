# Spec Delta: agent-coordinator — remote-control-coordinator

## ADDED: Event Bus Service

The coordinator SHALL provide a generalized event bus built on PostgreSQL LISTEN/NOTIFY that extends the existing `policy_sync.py` pattern to multiple channels.

### Requirements

- The event bus SHALL listen on the following PostgreSQL NOTIFY channels:
  - `coordinator_approval` — approval request submitted, decided, or expired
  - `coordinator_task` — task claimed, completed, or failed
  - `coordinator_agent` — agent registered, stale, or disconnected
  - `coordinator_status` — phase transitions, escalations, completion signals
  - `coordinator_guardrail` — destructive operation blocked
- The event bus SHALL support registering async callbacks per channel via `on_event(channel, callback)`.
- The event bus SHALL reconnect with exponential backoff (max 5 retries, base 1s) on connection loss, matching the `policy_sync.py` pattern.
- The event bus SHALL use a single dedicated asyncpg connection (not from the pool) for LISTEN.
- Database triggers SHALL emit NOTIFY on INSERT or UPDATE to `approval_queue`, `work_queue`, and `agent_discovery` tables.
- NOTIFY payloads SHALL be JSON objects containing at minimum: `event_type`, `entity_id`, `agent_id`, `timestamp`.

#### Scenario: Approval request triggers notification event

WHEN an approval request is inserted into `approval_queue`
THEN a `coordinator_approval` NOTIFY is emitted with payload `{"event_type": "submitted", "entity_id": "<request_id>", "agent_id": "<agent_id>", "operation": "<operation>"}`
AND the event bus dispatches to all registered callbacks for `coordinator_approval`.

#### Scenario: Task completion triggers notification event

WHEN a work queue task status changes to `completed` or `failed`
THEN a `coordinator_task` NOTIFY is emitted with payload `{"event_type": "<new_status>", "entity_id": "<task_id>", "agent_id": "<agent_id>"}`
AND the event bus dispatches to all registered callbacks for `coordinator_task`.

#### Scenario: Event bus reconnects on connection loss

WHEN the LISTEN connection drops
THEN the event bus SHALL retry with backoff delays of 1s, 2s, 4s, 8s, 16s
AND if all retries fail, the event bus SHALL log an error and stop (graceful degradation).

## ADDED: Notification Service

The coordinator SHALL provide a pluggable notification service that subscribes to the event bus and dispatches notifications through configured channels.

### Requirements

- The notifier SHALL implement a `NotificationChannel` protocol with methods: `send(event) -> bool`, `test() -> bool`, `supports_reply() -> bool`.
- The notifier SHALL maintain a registry of enabled channels, configured via the `NOTIFICATION_CHANNELS` environment variable (comma-separated list, e.g., `gmail,telegram,webhook`).
- The notifier SHALL dispatch events to all enabled channels in parallel via `asyncio.gather()`.
- The notifier SHALL classify events by urgency: `high` (immediate), `medium` (within 1 minute), `low` (batched into digest).
- High-urgency events: approval submitted, phase escalated, agent stale, guardrail triggered.
- Medium-urgency events: task completed, review completed, PR created, loop done.
- Low-urgency events: phase transitions, agent registered, lock acquired.
- The notifier SHALL support an event type filter per channel (configurable via env vars) to prevent unwanted notifications.
- If `NOTIFICATION_CHANNELS` is empty or unset, the notifier SHALL be disabled (no-op).

#### Scenario: Approval request sends immediate notification

WHEN an `approval.submitted` event arrives at the notifier
AND the event urgency is `high`
THEN the notifier SHALL dispatch to all enabled channels immediately
AND each channel receives a `CoordinatorEvent` with `event_type`, `urgency`, `change_id`, `agent_id`, `summary`, and `context` fields.

#### Scenario: No channels configured

WHEN `NOTIFICATION_CHANNELS` is empty
THEN the notifier SHALL not subscribe to the event bus
AND no notifications are sent.

## ADDED: Gmail Notification Channel

The coordinator SHALL provide a Gmail-compatible email channel with SMTP outbound and IMAP IDLE inbound for bidirectional communication.

### Requirements — Outbound (SMTP)

- The Gmail channel SHALL send notifications via SMTP using `aiosmtplib`.
- The Gmail channel SHALL support Gmail App Passwords and OAuth2 for authentication, configured via `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` environment variables.
- Email subjects SHALL include the change-id and a notification token in the format `[coordinator] <summary> [#<TOKEN>]`.
- Email bodies SHALL be HTML with: event summary, agent info, context details, and reply instructions.
- Emails SHALL use `In-Reply-To` and `References` headers to thread messages by change-id.
- The Gmail channel SHALL include custom headers: `X-Coordinator-Token`, `X-Coordinator-Event`, `X-Coordinator-Change-Id`.

#### Scenario: Approval notification email

WHEN the Gmail channel receives an `approval.submitted` event
THEN it sends an email with subject `[coordinator] Approval needed: <operation> [#<TOKEN>]`
AND the body includes agent name, operation description, resource, and reply instructions
AND a notification token is generated and stored with 1-hour TTL.

### Requirements — Inbound (IMAP IDLE)

- The Gmail channel SHALL monitor an IMAP mailbox using IMAP IDLE for near-real-time reply detection.
- The Gmail channel SHALL use `aioimaplib` for async IMAP operations.
- IMAP credentials SHALL be configured via `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD` environment variables.
- The Gmail channel SHALL reconnect and re-IDLE on timeout (29 minutes for Gmail) or connection loss.
- Reply parsing SHALL extract the token from: (a) subject line `[#TOKEN]` pattern, or (b) `In-Reply-To` header matching a sent message.
- Reply parsing SHALL recognize these commands (case-insensitive):
  - `approved`, `approve`, `yes` → approval decision: approved
  - `denied`, `deny`, `no` → approval decision: denied
  - `resolved` → re-trigger gate check for escalated auto-dev-loop
  - `skip` → bypass current phase
  - Any other text → free-text guidance injection into coordinator memory
- The Gmail channel SHALL validate the sender against `NOTIFICATION_ALLOWED_SENDERS` (comma-separated email allowlist).
- Invalid tokens (expired, already used, not found) SHALL result in a reply email explaining the error.

#### Scenario: Human approves via email reply

WHEN a human replies to an approval notification email with "approved"
AND the sender is in the allowed senders list
AND the token in the subject is valid and unexpired
THEN the Gmail channel SHALL call `ApprovalService.decide_request(request_id, "approved", decided_by=sender_email)`
AND the token SHALL be invalidated (single-use)
AND a confirmation email SHALL be sent: "Approved. Agent resuming."

#### Scenario: Reply with expired token

WHEN a human replies to a notification email
AND the token has expired (past TTL)
THEN the Gmail channel SHALL send a reply: "Token expired. Current pending approvals: [list]"
AND no coordinator action is taken.

#### Scenario: Reply from unauthorized sender

WHEN an email reply is received from an address not in `NOTIFICATION_ALLOWED_SENDERS`
THEN the reply SHALL be ignored
AND an audit log entry SHALL be created with the unauthorized attempt.

## ADDED: Notification Tokens

The coordinator SHALL manage short-lived, single-use tokens for secure reply-based interactions.

### Requirements

- Tokens SHALL be 8-character alphanumeric strings generated via `secrets.token_urlsafe`.
- Tokens SHALL be stored in a `notification_tokens` table with columns: `token`, `event_type`, `entity_id`, `change_id`, `created_at`, `expires_at`, `used_at`.
- Default TTL SHALL be 1 hour, configurable via `NOTIFICATION_TOKEN_TTL_SECONDS` (default: 3600).
- Tokens SHALL be single-use — the `used_at` column is set on first use, subsequent uses are rejected.
- Expired tokens SHALL be cleaned up by the watchdog service periodically.

#### Scenario: Token validation succeeds

WHEN a reply contains token `ABC12345`
AND the token exists in `notification_tokens` with `used_at IS NULL` and `expires_at > NOW()`
THEN validation succeeds
AND `used_at` is set to the current timestamp.

#### Scenario: Token reuse rejected

WHEN a reply contains a token that has already been used (`used_at IS NOT NULL`)
THEN validation fails with "Token already used".

## ADDED: Status Reporting

The coordinator SHALL accept status reports from agents via both Claude Code hooks and HTTP API.

### Requirements

- A new `POST /status/report` endpoint SHALL accept: `agent_id`, `change_id`, `phase`, `message`, `needs_human` (boolean), `metadata` (optional JSON).
- The endpoint SHALL update the agent's heartbeat timestamp as a side effect.
- If `needs_human` is true, the event SHALL be classified as `high` urgency.
- A `report_status.py` Claude Code hook script SHALL:
  - Fire on `Stop` and `SubagentStop` events.
  - Read `loop-state.json` if present to extract phase and finding trends.
  - Call `POST /status/report` with extracted data.
  - Complete within 5 seconds (timeout and fail silently on error).
  - Cache last-reported phase in `.status-cache.json` to avoid duplicate reports.
- The auto-dev-loop's `run_loop()` SHALL accept an optional `status_fn` callback with signature `(state: LoopState, event_type: str, message: str, urgent: bool) -> None`.

#### Scenario: Claude Code hook reports phase transition

WHEN a Claude Code `Stop` hook fires
AND `loop-state.json` exists with `current_phase` different from cached phase
THEN `report_status.py` SHALL call `POST /status/report` with the new phase
AND the coordinator emits a `coordinator_status` NOTIFY event.

#### Scenario: Codex agent reports status via HTTP

WHEN a Codex agent calls `POST /status/report` with `{"agent_id": "codex-1", "phase": "IMPL_REVIEW", "needs_human": false}`
THEN the coordinator stores the status and updates the heartbeat
AND emits a `coordinator_status` NOTIFY event with urgency `medium`.

## ADDED: Watchdog Service

The coordinator SHALL run a periodic health monitoring loop as an asyncio background task.

### Requirements

- The watchdog SHALL run within the `coordination_api.py` FastAPI lifespan (not a separate process).
- The watchdog SHALL check every 60 seconds (configurable via `WATCHDOG_INTERVAL_SECONDS`).
- The watchdog SHALL detect and notify on:
  - **Stale agents**: heartbeat older than 15 minutes → `high` urgency notification.
  - **Aging approvals**: pending approvals older than 15 minutes → `medium` urgency reminder (once, then every 30 minutes).
  - **Expiring locks**: locks within 10 minutes of TTL expiration → `medium` urgency warning to lock holder.
  - **Expired tokens**: clean up `notification_tokens` where `expires_at < NOW()`.
- The watchdog SHALL emit events via `pg_notify` to the event bus (same pathway as database triggers).
- The watchdog SHALL be disabled when `NOTIFICATION_CHANNELS` is empty (no point monitoring if nobody is listening).

#### Scenario: Stale agent detected

WHEN the watchdog finds an agent with `last_heartbeat` older than 15 minutes
AND the agent status is `active`
THEN it emits a `coordinator_agent` event with `event_type: "stale"` and urgency `high`
AND calls `cleanup_dead_agents()` to release the agent's locks.

#### Scenario: Aging approval reminder

WHEN the watchdog finds a pending approval older than 15 minutes
AND no reminder has been sent in the last 30 minutes for this approval
THEN it emits a `coordinator_approval` event with `event_type: "reminder"` and urgency `medium`.

## MODIFIED: Coordination API

### Requirements

- The `coordination_api.py` SHALL register the event bus and notifier in its FastAPI `lifespan` context manager.
- The `coordination_api.py` SHALL start the watchdog background task in the lifespan.
- A new `POST /notifications/test` endpoint SHALL send a test notification through all enabled channels and return per-channel success/failure.
- A new `GET /notifications/status` endpoint SHALL return the status of each configured channel (enabled, connected, last_sent).

## MODIFIED: Claude Code Hooks

### Requirements

- `.claude/hooks.json` SHALL add `Stop` and `SubagentStop` hook entries pointing to `agent-coordinator/scripts/report_status.py`.
- The hook script SHALL fail gracefully (exit 0) if the coordinator is not configured or unreachable.
- The hook script SHALL not block Claude Code for more than 5 seconds.
