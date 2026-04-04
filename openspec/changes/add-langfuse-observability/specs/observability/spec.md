# observability Delta Spec

**Change ID**: `add-langfuse-observability`
**Target Spec**: `observability` (extends)

## ADDED Requirements

### Requirement: Langfuse Tracing Module

The coordinator SHALL provide a Langfuse tracing module (`langfuse_tracing.py`) that manages a lazy-initialized Langfuse client, disabled by default.

- The module SHALL initialize the Langfuse client only when `LANGFUSE_ENABLED=true`
- The module SHALL be idempotent — calling `init_langfuse()` multiple times SHALL be a no-op after first initialization
- When `langfuse` package is not installed, initialization SHALL log a warning and fall back to no-op (no crash)
- When initialization fails for any reason, the module SHALL fall back to no-op and log a warning
- The module SHALL provide `create_trace()`, `create_span()`, and `end_span()` helpers that return `None` when disabled
- The module SHALL provide a `trace_operation()` context manager that creates a trace, yields it, records errors on exception, and flushes on exit
- The module SHALL provide `shutdown_langfuse()` that flushes pending events and releases the client
- The Langfuse client SHALL be initialized with `public_key`, `secret_key`, `host`, and `debug` from `LangfuseConfig`
- An empty `public_key` SHALL NOT cause a crash during initialization logging

#### Scenario: Langfuse disabled by default
- **WHEN** `LANGFUSE_ENABLED` is not set or is `false`
- **THEN** `init_langfuse()` sets `_langfuse = None`
- **AND** `get_langfuse()` returns `None`
- **AND** all trace/span helpers return `None` with zero overhead

#### Scenario: Langfuse enabled with valid config
- **WHEN** `LANGFUSE_ENABLED=true` and `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set
- **THEN** `init_langfuse()` creates a Langfuse client
- **AND** `get_langfuse()` returns the client instance
- **AND** `create_trace()` returns a trace object

#### Scenario: Langfuse package not installed
- **WHEN** `LANGFUSE_ENABLED=true` but `langfuse` package is not importable
- **THEN** initialization logs a warning with install instructions
- **AND** `get_langfuse()` returns `None`

#### Scenario: trace_operation records errors
- **WHEN** an exception is raised inside a `trace_operation()` context
- **THEN** the trace is updated with `level=ERROR` and the error message in output
- **AND** the exception is re-raised

### Requirement: Langfuse Configuration

The coordinator SHALL provide a `LangfuseConfig` dataclass with environment-based configuration for Langfuse integration.

- `LANGFUSE_ENABLED` (default: `false`) — master enable/disable toggle
- `LANGFUSE_PUBLIC_KEY` (default: `pk-lf-local-coding-agents`) — project public key
- `LANGFUSE_SECRET_KEY` (default: `sk-lf-local-coding-agents`) — project secret key
- `LANGFUSE_HOST` (default: `http://localhost:3050`) — Langfuse server URL
- `LANGFUSE_TRACE_API_REQUESTS` (default: `true`) — enable/disable HTTP request tracing middleware
- `LANGFUSE_DEBUG` (default: `false`) — enable SDK debug logging

#### Scenario: Default configuration
- **WHEN** no Langfuse environment variables are set
- **THEN** `LangfuseConfig.from_env()` returns `enabled=False`
- **AND** all other fields have sensible defaults for local development

#### Scenario: Trace API requests toggle
- **WHEN** `LANGFUSE_TRACE_API_REQUESTS=false`
- **THEN** the HTTP tracing middleware SHALL NOT be registered on the FastAPI app

### Requirement: HTTP Request Tracing Middleware

The coordinator HTTP API SHALL provide optional Langfuse middleware that traces API requests from cloud agents.

- The middleware SHALL create a Langfuse trace per request with operation name `api:<path>`
- The middleware SHALL resolve agent identity from the `X-API-Key` header via config
- The middleware SHALL skip tracing for health/metrics/docs paths (`/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`)
- The middleware SHALL capture HTTP method, path, agent ID, session ID (from `X-Session-Id` header), status code, and duration
- The middleware SHALL finalize traces with `level=ERROR` for 5xx, `WARNING` for 4xx, `DEFAULT` otherwise
- The middleware SHALL finalize traces even when `call_next` raises an exception (recording status 500)
- The middleware SHALL NOT flush Langfuse per-request — it SHALL rely on SDK batching and shutdown flush
- The middleware SHALL only be registered when `get_langfuse() is not None` AND `config.langfuse.trace_api_requests` is `True`
- Agent identity resolution failures SHALL NOT crash the request — fall back to `"cloud-agent"`

#### Scenario: API request traced
- **WHEN** a cloud agent sends `POST /locks/acquire` with `X-API-Key: key1`
- **THEN** middleware creates a trace named `api:locks/acquire` with `user_id` resolved from key1
- **AND** a span is created for `POST /locks/acquire`
- **AND** trace and span are finalized with status code, duration, and level

#### Scenario: Health check not traced
- **WHEN** a request is made to `GET /health`
- **THEN** no Langfuse trace is created
- **AND** the request passes through to the handler directly

#### Scenario: Middleware handles downstream errors
- **WHEN** `call_next` raises an unhandled exception
- **THEN** the trace is finalized with status 500 and `level=ERROR`
- **AND** the exception is re-raised to the ASGI error handler

### Requirement: Claude Code Session Tracing Hook

The coordinator SHALL provide a Claude Code Stop hook (`langfuse_hook.py`) that sends session transcripts to Langfuse incrementally.

- The hook SHALL only run when `LANGFUSE_ENABLED=true` and both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set
- The hook SHALL find the most recently modified transcript file under `~/.claude/projects/`
- The hook SHALL track processing state per session in `~/.claude/state/langfuse_state_<hash>.json`
- The hook SHALL advance the state cursor by **lines consumed** (not messages parsed) to handle blank and invalid JSON lines correctly
- The hook SHALL group messages into conversation turns (user → assistant + tool calls)
- The hook SHALL create a Langfuse trace per turn with user input, assistant output, model info, and tool call spans
- The hook SHALL sanitize all text before sending to Langfuse, redacting:
  - Anthropic/OpenAI API keys (`sk-*`)
  - Langfuse keys (`pk-lf-*`, `sk-lf-*`)
  - Supabase service keys (`sbp_*`)
  - JWT tokens (`eyJ*`)
  - Bearer tokens
  - Generic key=value secret patterns (`password=`, `secret=`, `token=`, `api_key=`, `apikey=`)
- Sanitization patterns SHALL be ordered from most specific to most general to preserve descriptive redaction markers
- The hook SHALL create the Langfuse client with `timeout=5` to limit blocking when the server is unreachable
- The hook SHALL handle client creation failures gracefully (log warning, return 0)
- The hook SHALL advance the cursor even when no complete turns are found (to avoid re-reading orphan messages)

#### Scenario: Incremental transcript processing
- **WHEN** the hook runs and the transcript has 10 new lines since last run, 2 of which are blank
- **THEN** the hook processes 8 valid messages
- **AND** advances the cursor by 10 (lines consumed, not messages parsed)

#### Scenario: Secret sanitization
- **WHEN** a tool output contains `sk-lf-local-coding-agents` and `password=secret123`
- **THEN** the Langfuse trace input/output contains `LF-KEY-REDACTED` and `password=REDACTED`
- **AND** the original secret values do not appear in the Langfuse trace

#### Scenario: Langfuse server unreachable
- **WHEN** `LANGFUSE_ENABLED=true` but the Langfuse server at `LANGFUSE_HOST` is not reachable
- **THEN** the hook logs a warning and returns without sending traces
- **AND** the state cursor is NOT advanced (so messages will be retried on next run)

### Requirement: Self-Hosted Langfuse Stack

The docker-compose file SHALL support a self-hosted Langfuse v3 stack behind a `langfuse` profile.

- The stack SHALL include: Langfuse web, Langfuse worker, ClickHouse, Redis, MinIO
- The stack SHALL reuse the existing Postgres service (creating a separate `langfuse` database via init container)
- The stack SHALL be gated behind the `langfuse` Docker profile — not started by default
- The stack SHALL auto-provision a default project with known API keys for local development
- The Langfuse UI SHALL be accessible at `http://localhost:${LANGFUSE_PORT:-3050}`

#### Scenario: Start Langfuse stack
- **WHEN** operator runs `docker compose --profile langfuse up -d`
- **THEN** Langfuse web, worker, ClickHouse, Redis, and MinIO containers start
- **AND** a `langfuse` database is created in Postgres if it doesn't exist
- **AND** a default project is provisioned with `pk-lf-local-coding-agents` / `sk-lf-local-coding-agents`

#### Scenario: Default profile excludes Langfuse
- **WHEN** operator runs `docker compose up -d` without `--profile langfuse`
- **THEN** no Langfuse-related containers are started

### Requirement: Setup Script

The coordinator SHALL provide a setup script (`setup_langfuse.sh`) for configuring Langfuse integration.

- `--local` mode SHALL start the self-hosted stack and install the Claude Code hook
- `--cloud` mode SHALL configure for Langfuse Cloud (override localhost default to `https://cloud.langfuse.com`)
- `--cloud` mode SHALL require non-default `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
- `--install-hook` mode SHALL install only the Claude Code hook without starting services
- The setup script SHALL detect when `LANGFUSE_HOST` still has the localhost default in `--cloud` mode and override it

#### Scenario: Cloud mode overrides localhost host
- **WHEN** operator runs `setup_langfuse.sh --cloud` without exporting `LANGFUSE_HOST`
- **THEN** the script sets `LANGFUSE_HOST=https://cloud.langfuse.com`
- **AND** the hook is configured to send traces to Langfuse Cloud
