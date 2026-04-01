# Spec Delta: agent-coordinator — remote-control-coordinator

## Definitions

### CoordinatorEvent Schema

All events flowing through the event bus and notifier SHALL conform to this schema:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_type` | `str` | Yes | Dot-separated event identifier (e.g., `approval.submitted`, `agent.stale`) |
| `channel` | `str` | Yes | NOTIFY channel name (e.g., `coordinator_approval`) |
| `entity_id` | `str (UUID)` | Yes | Primary resource ID: `request_id` for approval events, `task_id` for task events, `agent_id` for agent events, `change_id` for status/guardrail events |
| `agent_id` | `str` | Yes | Agent that caused or is subject to the event |
| `change_id` | `str \| None` | No | OpenSpec change-id if applicable |
| `urgency` | `Literal["low", "medium", "high"]` | Yes | Dispatch urgency classification |
| `summary` | `str` | Yes | Human-readable summary, max 200 characters |
| `context` | `dict[str, Any]` | No | Structured event-specific details (operation, resource, findings, etc.) |
| `timestamp` | `str (ISO 8601)` | Yes | Event creation time |

## ADDED Requirements

### Requirement: Event Bus Service

The coordinator SHALL provide a generalized event bus built on PostgreSQL LISTEN/NOTIFY that extends the existing `policy_sync.py` pattern to multiple channels.

- The event bus SHALL listen on the following PostgreSQL NOTIFY channels:
  - `coordinator_approval` — approval request submitted, decided, or expired (trigger on `approval_queue`)
  - `coordinator_task` — task claimed, completed, or failed (trigger on `work_queue`)
  - `coordinator_agent` — agent registered, stale, or disconnected (trigger on `agent_discovery`)
  - `coordinator_status` — phase transitions, escalations, completion signals (emitted by `POST /status/report` and watchdog via direct `pg_notify`)
- The event bus SHALL support registering async callbacks per channel via `on_event(channel, callback)`.
- The event bus SHALL reconnect with exponential backoff (max 5 retries, base 1s) on connection loss, matching the `policy_sync.py` pattern.
- The event bus SHALL use a single dedicated asyncpg connection (not from the pool) for LISTEN.
- Database triggers SHALL emit NOTIFY on INSERT or UPDATE to `approval_queue`, `work_queue`, and `agent_discovery` tables.
- NOTIFY payloads SHALL be JSON objects conforming to the CoordinatorEvent schema.
- If a NOTIFY payload exceeds 7KB (leaving 1KB margin below PostgreSQL's 8KB limit), the `context` field SHALL be truncated and a `"[context truncated]"` marker added.
- The event bus MUST NOT emit NOTIFY events in response to changes made by the coordinator itself (e.g., watchdog-initiated cleanups). Triggers SHALL check `current_setting('app.coordinator_internal')` and skip NOTIFY when set to `'true'`.

#### Scenario: Approval request triggers notification event

WHEN an approval request is inserted into `approval_queue`
THEN a `coordinator_approval` NOTIFY is emitted with payload `{"event_type": "approval.submitted", "entity_id": "<request_id>", "agent_id": "<agent_id>", "urgency": "high", "summary": "Approval needed: <operation>", "context": {"operation": "<operation>", "resource": "<resource>"}}`
AND the event bus dispatches to all registered callbacks for `coordinator_approval`.

#### Scenario: Task completion triggers notification event

WHEN a work queue task status changes to `completed` or `failed`
THEN a `coordinator_task` NOTIFY is emitted with payload `{"event_type": "task.<new_status>", "entity_id": "<task_id>", "agent_id": "<agent_id>", "urgency": "medium"}`
AND the event bus dispatches to all registered callbacks for `coordinator_task`.

#### Scenario: Event bus reconnects on connection loss

WHEN the LISTEN connection detects `ConnectionDoesNotExistError` or receives no data for 60 seconds
THEN the event bus SHALL retry with backoff delays of 1s, 2s, 4s, 8s, 16s
AND if all 5 retries fail, the event bus SHALL log a CRITICAL error, set an internal `failed` flag, and cease listening.

#### Scenario: Event bus exhausts retries

WHEN the event bus has failed all reconnection attempts
THEN the watchdog (if running) SHALL detect the failed flag within one check interval
AND emit a `high` urgency notification via direct `pg_notify` call (bypassing the failed listener)
AND the event bus SHALL NOT attempt further reconnections until manually restarted or the API server restarts.

### Requirement: Notification Service

The coordinator SHALL provide a pluggable notification service that subscribes to the event bus and dispatches notifications through configured channels.

- The notifier SHALL implement a `NotificationChannel` protocol with methods: `send(event) -> bool`, `test() -> bool`, `supports_reply() -> bool`.
- The notifier SHALL maintain a registry of enabled channels, configured via the `NOTIFICATION_CHANNELS` environment variable (comma-separated list, e.g., `gmail,telegram,webhook`).
- The notifier SHALL dispatch events to all enabled channels in parallel via `asyncio.gather()`.
- The notifier SHALL classify events by urgency: `high` (immediate), `medium` (within 1 minute), `low` (batched into digest).
- High-urgency events: approval submitted, phase escalated, agent stale, `needs_human=true` status reports, event bus connection failure.
- Medium-urgency events: task completed, review completed, PR created, loop done.
- Low-urgency events: phase transitions, agent registered, lock acquired.
- The notifier SHALL support an event type filter per channel via `NOTIFICATION_EVENT_FILTER_{CHANNEL}` env var (comma-separated event types, e.g., `approval.submitted,agent.stale`). Events not matching the filter SHALL be silently dropped for that channel.
- If `NOTIFICATION_CHANNELS` is empty or unset, the notifier SHALL be disabled (no-op).
- If a channel's `send()` raises an exception, the notifier SHALL catch the exception, log a WARNING, and continue dispatching to remaining channels. The notifier SHALL return a dict of per-channel success/failure results.
- The notifier SHALL retry failed channel sends with exponential backoff (base 2s, max 60s, up to 3 attempts) before marking the send as failed.
- Low-urgency events SHALL be collected into a digest batch and sent every `NOTIFICATION_DIGEST_INTERVAL_SECONDS` seconds (default: 600, i.e., 10 minutes). The digest SHALL contain: event count, per-type summary, and the 5 most recent event summaries. Max batch size: 100 events (oldest dropped if exceeded).
- The notifier MUST NOT dispatch notifications for events originating from the notifier itself or the watchdog (preventing notification loops). Events with `context.source == "notifier"` or `context.source == "watchdog"` SHALL be skipped.

**Testing Strategy:**

- All channel implementations SHALL have a corresponding `Fake` test double implementing the `NotificationChannel` protocol (e.g., `GmailChannelFake`) that buffers sent events in a list for assertion.
- `NotifierService` unit tests SHALL use fake channels exclusively (no real SMTP/IMAP).
- Integration tests requiring real SMTP/IMAP SHALL be marked `@pytest.mark.integration` and skipped in CI by default.
- Time-dependent tests SHALL inject a `time_fn` parameter (default `time.monotonic`) and use `freezegun` or `time-machine` to advance time deterministically.

#### Scenario: Approval request sends immediate notification

WHEN an `approval.submitted` event arrives at the notifier
AND the event urgency is `high`
THEN the notifier SHALL dispatch to all enabled channels immediately (within 1 second)
AND each channel's `send()` receives a `CoordinatorEvent` conforming to the schema defined in Definitions.

#### Scenario: No channels configured

WHEN `NOTIFICATION_CHANNELS` is empty
THEN the notifier SHALL not subscribe to the event bus
AND no notifications are sent.

#### Scenario: One channel fails during dispatch

WHEN the notifier dispatches an event to 3 channels
AND the second channel's `send()` raises `SMTPConnectionError`
THEN the notifier SHALL log a WARNING for the failed channel
AND the first and third channels SHALL still receive the event
AND the return value SHALL be `{"gmail": False, "telegram": True, "webhook": True}`.

#### Scenario: Low-urgency events batched into digest

WHEN 5 low-urgency events arrive within a 10-minute window
THEN the notifier SHALL NOT send them immediately
AND after 10 minutes (or `NOTIFICATION_DIGEST_INTERVAL_SECONDS`), the notifier SHALL send a single digest email containing all 5 event summaries.

### Requirement: Gmail Notification Channel

The coordinator SHALL provide a Gmail-compatible email channel with SMTP outbound and IMAP IDLE inbound for bidirectional communication.

Outbound (SMTP):

- The Gmail channel SHALL send notifications via SMTP using `aiosmtplib`.
- The Gmail channel SHALL support Gmail App Passwords for authentication, configured via `SMTP_HOST` (default: `smtp.gmail.com`), `SMTP_PORT` (default: `587`), `SMTP_USER`, `SMTP_PASSWORD` environment variables. OAuth2 support is deferred to a future change.
- Email subjects SHALL include the change-id and a notification token in the format `[coordinator] <summary> [#<TOKEN>]`.
- Email bodies SHALL be HTML with: event summary, agent info, context details, and reply instructions.
- Emails SHALL use `In-Reply-To` and `References` headers to thread messages by change-id.
- The Gmail channel SHALL include custom headers: `X-Coordinator-Token`, `X-Coordinator-Event`, `X-Coordinator-Change-Id`.

#### Scenario: Approval notification email

WHEN the Gmail channel receives an `approval.submitted` event
THEN it sends an email with subject `[coordinator] Approval needed: <operation> [#<TOKEN>]`
AND the body includes agent name, operation description, resource, and reply instructions
AND a notification token is generated and stored with 1-hour TTL.

Inbound (IMAP IDLE):

- The Gmail channel SHALL monitor an IMAP mailbox using IMAP IDLE for near-real-time reply detection.
- The Gmail channel SHALL use `aioimaplib` for async IMAP operations.
- IMAP credentials SHALL be configured via `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD` environment variables.
- The Gmail channel SHALL reconnect and re-IDLE on timeout (29 minutes for Gmail) or connection loss.
- Reply parsing SHALL extract the token from: (a) subject line `[#TOKEN]` pattern, or (b) `In-Reply-To` header matching a sent message.
- Reply parsing SHALL extract the token using this precedence: (1) regex match `\[#([A-Za-z0-9]{8})\]` in subject line, (2) `In-Reply-To` header matching a previously sent `Message-ID`. If neither yields a token, the reply SHALL be ignored.
- Reply parsing SHALL split the reply body by whitespace, strip punctuation from the first word, and match case-insensitively against the command set. Multi-line replies SHALL treat the first line as the command; remaining lines are appended as guidance context.
- Reply parsing SHALL recognize these commands (case-insensitive, first word only):
  - `approved`, `approve`, `yes` → calls `ApprovalService.decide_request(request_id, "approved", decided_by=sender_email)`
  - `denied`, `deny`, `no` → calls `ApprovalService.decide_request(request_id, "denied", decided_by=sender_email)`
  - `resolved` → calls `POST /status/report` with `{"event_type": "gate_check", "change_id": "<from_token>", "message": "Human confirmed resolved"}`, which the auto-dev-loop's gate check evaluates on next iteration
  - `skip` → calls `POST /status/report` with `{"event_type": "phase_skip", "change_id": "<from_token>", "message": "Human requested phase skip"}`
  - Any other text → calls `MemoryService.remember(event_type="guidance", content=<reply_text>, tags=["human-feedback", change_id])` for injection into the next convergence round
- The Gmail channel SHALL validate the sender by extracting the email address from the IMAP envelope and matching case-insensitively against `NOTIFICATION_ALLOWED_SENDERS` (comma-separated email allowlist). No domain wildcards.
- Invalid tokens (expired, already used, not found) SHALL result in a reply email explaining the specific error. If expired, the reply SHALL include a list of current pending approvals (if any).

Security Prohibitions:

- The relay MUST NOT execute arbitrary shell commands or code derived from email content.
- The relay MUST NOT allow approval decisions from addresses not in `NOTIFICATION_ALLOWED_SENDERS`.
- The relay MUST NOT reuse or re-validate an invalidated token.
- The relay MUST NOT include secrets, API keys, or internal URLs in outbound notification emails.
- The relay MUST NOT process email attachments — only the plain-text body is parsed.

#### Scenario: Human approves via email reply

WHEN a human replies to an approval notification email with "approved"
AND the sender is in the allowed senders list
AND the token in the subject is valid and unexpired
THEN the Gmail channel SHALL call `ApprovalService.decide_request(request_id, "approved", decided_by=sender_email)`
AND the token SHALL be invalidated (single-use)
AND a confirmation email SHALL be sent: "Approved. Agent resuming."

#### Scenario: Concurrent replies for same approval

WHEN two humans reply to the same approval notification simultaneously
THEN the first reply to reach the database SHALL set `used_at = NOW()` via `UPDATE ... WHERE used_at IS NULL` (atomic)
AND the second reply SHALL receive "Token already used" error
AND no duplicate coordinator action is taken.

#### Scenario: Reply with expired token

WHEN a human replies to a notification email
AND the token has expired (past TTL)
THEN the Gmail channel SHALL send a reply: "Token expired. Current pending approvals: [list]"
AND no coordinator action is taken.

#### Scenario: Reply from unauthorized sender

WHEN an email reply is received from an address not in `NOTIFICATION_ALLOWED_SENDERS`
THEN the reply SHALL be ignored (no response sent)
AND an audit log entry SHALL be created with `operation: "unauthorized_reply"`, `agent_id: "<sender_email>"`.

#### Scenario: Human replies "resolved" to escalation notification

WHEN a human replies "resolved" to an escalation notification
AND the token is valid
THEN the relay SHALL call `POST /status/report` with `event_type: "gate_check"` and `change_id` from the token
AND the coordinator SHALL store this as a status event in the `coordinator_status` NOTIFY channel
AND a confirmation email SHALL be sent: "Gate check triggered. Loop will re-evaluate."

Note: The auto-dev-loop's existing `gate_check_fn` callback (already defined in `auto_dev_loop.py`) polls coordinator state. When it sees a `gate_check` status event for its change-id, it re-evaluates the escalation condition. No new callback parameter is needed — `gate_check_fn` is already part of `run_loop()`'s signature.

#### Scenario: Human replies with free-text guidance

WHEN a human replies with "The API should use REST conventions, not RPC style"
AND the token is valid
THEN the relay SHALL store the text via `MemoryService.remember()` with tags `["human-feedback", "<change_id>"]`
AND a confirmation email SHALL be sent: "Guidance recorded. Will be available in next review round."

### Requirement: Notification Tokens

The coordinator SHALL manage short-lived, single-use tokens for secure reply-based interactions.

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

### Requirement: Status Reporting

The coordinator SHALL accept status reports from agents via both Claude Code hooks and HTTP API.

- A new `POST /status/report` endpoint SHALL accept: `agent_id`, `change_id`, `phase`, `message`, `needs_human` (boolean), `event_type` (optional, default: `"phase_transition"`), `metadata` (optional JSON).
- The endpoint SHALL update the agent's heartbeat timestamp as a side effect.
- If `needs_human` is true, the event SHALL be classified as `high` urgency.
- The endpoint SHALL emit a `coordinator_status` NOTIFY event for all status reports.
- Special `event_type` values have semantic meaning for the auto-dev-loop:
  - `gate_check` — signals that a human has confirmed an escalation is resolved. The auto-dev-loop's `gate_check_fn` SHALL query for recent `gate_check` events for its `change_id` and re-evaluate the escalation condition if found.
  - `phase_skip` — signals that a human wants to bypass the current phase. The auto-dev-loop's `gate_check_fn` SHALL query for recent `phase_skip` events and return `True` (resolved) if found, causing the loop to exit ESCALATE and proceed to the next phase.
- A `report_status.py` Claude Code hook script SHALL:
  - Fire on `Stop` and `SubagentStop` events.
  - Read `loop-state.json` if present to extract `current_phase` and `findings_trend`.
  - If `loop-state.json` is missing or contains invalid JSON, report `phase: "UNKNOWN"` and log a warning to stderr.
  - Compare `current_phase` against `.status-cache.json` — only report if phase has changed.
  - Call `POST /status/report` with extracted data.
  - Run the HTTP call with a hard 5-second timeout (`subprocess` or `httpx` with `timeout=5.0`). If the coordinator is unreachable or the call times out, log to stderr and exit 0 (do NOT block Claude Code).
  - Exit 0 in all cases (success, timeout, error) — the hook MUST NOT block the agent.
  - Update `.status-cache.json` with the reported phase on success.
- The auto-dev-loop's `run_loop()` SHALL accept an optional `status_fn` callback with signature `(state: LoopState, event_type: str, message: str, urgent: bool) -> None`.
- If `status_fn` raises an exception or exceeds 5 seconds, the exception SHALL be caught and logged. The loop SHALL NOT crash or change behavior due to `status_fn` failures. The error SHALL be included as `error_details` in the next heartbeat.
- **Two code paths** (both produce equivalent `coordinator_status` NOTIFY events):
  - **Path A (in-band callback)**: `run_loop()` calls `status_fn` at phase transitions. The callback delegates to `report_status` MCP tool (local) or `POST /status/report` (HTTP). Works for all agents (Claude, Codex, Gemini).
  - **Path B (out-of-band hook)**: Claude Code `Stop` hook fires `report_status.py`, which reads `loop-state.json` independently and POSTs to `/status/report`. Claude Code-specific; provides implicit heartbeat.

#### Scenario: Claude Code hook reports phase transition

WHEN a Claude Code `Stop` hook fires
AND `loop-state.json` exists with `current_phase` different from cached phase
THEN `report_status.py` SHALL call `POST /status/report` with the new phase
AND the coordinator emits a `coordinator_status` NOTIFY event.

#### Scenario: Codex agent reports status via HTTP

WHEN a Codex agent calls `POST /status/report` with `{"agent_id": "codex-1", "phase": "IMPL_REVIEW", "needs_human": false}`
THEN the coordinator stores the status and updates the heartbeat
AND emits a `coordinator_status` NOTIFY event with urgency `medium`.

### Requirement: Watchdog Service

The coordinator SHALL run a periodic health monitoring loop as an asyncio background task.

- The watchdog SHALL run within the `coordination_api.py` FastAPI lifespan (not a separate process).
- The watchdog SHALL check every 60 seconds (configurable via `WATCHDOG_INTERVAL_SECONDS`, range 10-3600, default: 60).
- The watchdog SHALL detect and notify on:
  - **Stale agents**: heartbeat older than 15 minutes → `high` urgency notification, then call `cleanup_dead_agents()`.
  - **Aging approvals**: pending approvals older than 15 minutes → `medium` urgency reminder. Reminders SHALL be debounced by storing `last_reminder_at` in a `watchdog_state` in-memory dict keyed by `approval_id`. Re-send only if `last_reminder_at` is older than 30 minutes. On coordinator restart, debounce state resets (acceptable — first check after restart sends reminders for all aging approvals).
  - **Expiring locks**: locks within 10 minutes of TTL expiration → `medium` urgency warning to lock holder.
  - **Expired tokens**: DELETE from `notification_tokens` WHERE `expires_at < NOW()`.
  - **Event bus health**: if event bus `failed` flag is set, emit a `high` urgency notification via direct `pg_notify` (not through the failed listener) and attempt to restart the event bus.
  - **Stale agent with pending approvals**: if a stale agent is cleaned up AND `approval_queue` has pending requests from that agent, those approvals SHALL be expired and a notification sent.
- The watchdog SHALL emit events via direct `pg_notify` call (using the coordinator's database connection, not through the event bus listener) to ensure notifications work even if the event bus is down.
- The watchdog SHALL NOT block if `pg_notify` fails — log error and continue to next check.
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

## ADDED Requirements (Coordination API + Hooks)

### Requirement: Coordination API

- The `coordination_api.py` SHALL register the event bus and notifier in its FastAPI `lifespan` context manager.
- The `coordination_api.py` SHALL start the watchdog background task in the lifespan.
- A new `POST /notifications/test` endpoint SHALL send a test notification through all enabled channels and return per-channel success/failure.
- A new `GET /notifications/status` endpoint SHALL return the status of each configured channel (enabled, connected, last_sent).

#### Scenario: API lifespan starts event bus and notifier

WHEN the FastAPI application starts
THEN the event bus connects and begins listening on all channels
AND the notifier subscribes to the event bus
AND the watchdog background task begins periodic checks.

### Requirement: Claude Code Hooks

- `.claude/hooks.json` SHALL add `Stop` and `SubagentStop` hook entries pointing to `agent-coordinator/scripts/report_status.py`.
- The hook script SHALL fail gracefully (exit 0) if the coordinator is not configured or unreachable.
- The hook script SHALL not block Claude Code for more than 5 seconds.

#### Scenario: Hook fires on Stop event

WHEN Claude Code fires a Stop event
AND `loop-state.json` exists with a new phase
THEN `report_status.py` sends a status report to the coordinator
AND exits with code 0 regardless of coordinator response.
