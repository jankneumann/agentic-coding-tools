# observability Delta Spec: add-langfuse-observability

## ADDED Requirements

### Requirement: Langfuse Client Module and Configuration

The coordinator SHALL provide a `langfuse_tracing` module that initializes a Langfuse client for LLM session observability, complementing the existing OpenTelemetry infrastructure metrics. The module SHALL follow the same lazy-init, env-var-gated, no-op-fallback pattern as `telemetry.py`.

- The coordinator SHALL expose a `LangfuseConfig` dataclass in `config.py` with environment variable control
- When `LANGFUSE_ENABLED` is not `true`, all Langfuse operations SHALL be no-ops with zero overhead
- The Langfuse SDK dependency (`langfuse>=3.0,<4.0`) MUST be in the existing `[observability]` optional extras group
- The `init_langfuse()` function SHALL be called during HTTP API startup alongside `init_telemetry()`
- The module SHALL provide `create_trace()`, `create_span()`, `end_span()`, and `trace_operation()` helpers
- The module SHALL flush pending events and shut down the client on HTTP API lifespan shutdown

#### Scenario: Langfuse enabled with self-hosted instance
- **WHEN** `LANGFUSE_ENABLED=true` and `LANGFUSE_HOST=http://localhost:3050`
- **AND** `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set
- **THEN** system initializes Langfuse client connected to the configured host
- **AND** `create_trace()` returns a trace object that can be enriched with spans
- **AND** `get_langfuse()` returns the initialized client instance

#### Scenario: Langfuse disabled (default)
- **WHEN** `LANGFUSE_ENABLED` is not set or is `false`
- **THEN** `init_langfuse()` returns immediately with no side effects
- **AND** `get_langfuse()` returns `None`
- **AND** `create_trace()` and `create_span()` return `None` (no-op)
- **AND** no network connections are established to any Langfuse host

#### Scenario: Langfuse SDK not installed
- **WHEN** `LANGFUSE_ENABLED=true` but the `langfuse` package is not installed
- **THEN** `init_langfuse()` logs a warning with installation instructions
- **AND** falls back to no-op behavior (same as disabled)
- **AND** does not raise an import error

---

### Requirement: Coordinator API Tracing Middleware

The coordinator HTTP API SHALL include FastAPI middleware that traces all API requests to Langfuse, providing server-side observability for cloud agent interactions.

- Every coordinator HTTP API request (except health/metrics/docs endpoints) SHALL create a Langfuse trace with the operation name, agent identity, HTTP method, and path
- The middleware SHALL resolve agent identity from the `X-API-Key` header using `config.api.api_key_identities`
- Cloud agents MAY pass an `X-Session-Id` header to group their traces into coherent sessions in Langfuse
- The middleware SHALL record HTTP status codes and request duration on trace completion
- When Langfuse is disabled, the middleware SHALL pass requests through with zero overhead

#### Scenario: Cloud agent API request traced
- **WHEN** a cloud agent with API key bound to `codex-1` sends `POST /locks/acquire`
- **AND** Langfuse is enabled
- **THEN** a Langfuse trace is created with `name="api:locks/acquire"` and `user_id="codex-1"`
- **AND** a child span records the request duration and HTTP status code
- **AND** the trace is tagged with `["coordinator", "api-request", "post"]`

#### Scenario: Session grouping via header
- **WHEN** a cloud agent includes `X-Session-Id: session-abc-123` in the request
- **THEN** the Langfuse trace is created with `session_id="session-abc-123"`
- **AND** all traces with the same session ID appear grouped in the Langfuse UI

#### Scenario: Health endpoints excluded from tracing
- **WHEN** a request is made to `/health`, `/metrics`, `/docs`, or `/openapi.json`
- **THEN** no Langfuse trace is created for the request

#### Scenario: Error responses traced with ERROR level
- **WHEN** an API request returns HTTP 5xx status
- **THEN** the Langfuse trace and span are marked with `level="ERROR"`
- **AND** the status message includes the HTTP status code

---

### Requirement: Claude Code Stop Hook for Session Tracing

The coordinator SHALL provide a Claude Code Stop hook script that parses session transcripts and sends conversation turns to Langfuse as traces with nested tool call spans.

- The hook SHALL read `transcript.jsonl` files from Claude Code's project directory (`~/.claude/projects/`)
- The hook SHALL process incrementally: only new messages since the last run, using a state file in `~/.claude/state/`
- Each conversation turn SHALL become a Langfuse trace with the user message as input and assistant response as output
- Each tool call within a turn SHALL become a child span with tool name, input parameters, and output
- The hook SHALL sanitize traces to redact API keys, bearer tokens, and password patterns
- The hook SHALL group all traces from one session using Langfuse's `session_id` parameter
- The hook SHALL exit silently (exit code 0) on any error to avoid blocking Claude Code

#### Scenario: Single conversation turn traced
- **WHEN** a Claude Code session produces a turn with user message "Read the file" and assistant response with a Read tool call
- **THEN** the hook creates a Langfuse trace with `input="Read the file"` and `output=<assistant response>`
- **AND** a child span `tool:Read` is created with the tool's input parameters and output

#### Scenario: Incremental processing
- **WHEN** the hook has previously processed 10 messages (state: `last_line=10`)
- **AND** the transcript now has 15 messages
- **THEN** the hook processes only messages 11-15
- **AND** updates state to `last_line=15`

#### Scenario: Secret redaction
- **WHEN** a message contains `sk-abcdef1234567890abcdef1234567890`
- **THEN** the trace input/output contains `SK-REDACTED` instead of the API key

#### Scenario: Hook disabled
- **WHEN** `LANGFUSE_ENABLED` is not `true`
- **THEN** the hook exits immediately without reading any transcript files

---

### Requirement: Self-Hosted Langfuse Infrastructure

The coordinator's Docker Compose configuration SHALL include a Langfuse v3 self-hosted stack under the `langfuse` profile, reusing the existing ParadeDB Postgres instance.

- Langfuse services SHALL be activated with `docker compose --profile langfuse up -d`
- Langfuse SHALL use a separate `langfuse` database on the existing Postgres instance (NOT a separate Postgres container)
- The stack SHALL include: langfuse-web, langfuse-worker, ClickHouse (analytics), Redis (queue/cache), MinIO (blob storage)
- An init container SHALL create the `langfuse` database on first startup
- The Langfuse UI SHALL be accessible at `http://localhost:${LANGFUSE_PORT:-3050}`
- Default credentials and API keys SHALL be pre-configured for development use

#### Scenario: Langfuse stack starts with profile
- **WHEN** operator runs `docker compose --profile langfuse up -d`
- **THEN** all Langfuse services start alongside the existing Postgres service
- **AND** the `langfuse` database is created automatically on the existing Postgres instance
- **AND** `curl http://localhost:3050/api/public/health` returns healthy status

#### Scenario: Langfuse does not start without profile
- **WHEN** operator runs `docker compose up -d` (without `--profile langfuse`)
- **THEN** only the Postgres (and optionally OpenBao) services start
- **AND** no Langfuse-related containers are created

#### Scenario: Existing Postgres data preserved
- **WHEN** the Langfuse profile is activated on an existing Postgres instance with coordinator data
- **THEN** all existing coordinator tables and data in the `postgres` database are unaffected
- **AND** Langfuse uses only the separate `langfuse` database

---

### Requirement: Setup and Deployment Script

The coordinator SHALL provide a setup script supporting self-hosted, cloud, and BYOL (bring-your-own-Langfuse) deployment modes.

- `scripts/setup_langfuse.sh --local` SHALL start the self-hosted stack and install the Claude Code hook
- `scripts/setup_langfuse.sh --cloud` SHALL configure for Langfuse Cloud (requires pre-set API keys)
- `scripts/setup_langfuse.sh --install-hook` SHALL install only the Claude Code Stop hook
- `scripts/setup_langfuse.sh --check` SHALL verify Langfuse health and API key connectivity

#### Scenario: Local setup
- **WHEN** operator runs `./scripts/setup_langfuse.sh --local`
- **THEN** the Langfuse Docker stack starts with `docker compose --profile langfuse up -d`
- **AND** the hook script is copied to `~/.claude/hooks/langfuse_hook.py`
- **AND** the operator is shown the required `~/.claude/settings.json` configuration

#### Scenario: Health check
- **WHEN** operator runs `./scripts/setup_langfuse.sh --check`
- **THEN** the script checks `${LANGFUSE_HOST}/api/public/health` and reports status
