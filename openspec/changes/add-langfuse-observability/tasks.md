# Tasks: add-langfuse-observability

## 1. Core Tracing Module
**Files**: `src/langfuse_tracing.py`, `src/config.py`
**Dependencies**: None

- [x] 1.1 Add `LangfuseConfig` dataclass to `config.py` with env-based construction
- [x] 1.2 Implement lazy-initialized Langfuse client module
- [x] 1.3 Implement `create_trace()`, `create_span()`, `end_span()` helpers
- [x] 1.4 Implement `trace_operation()` context manager with error recording
- [x] 1.5 Implement `shutdown_langfuse()` with flush + shutdown
- [x] 1.6 Add `reset_langfuse()` for test isolation
- [x] 1.7 Guard against empty `public_key` in init log message

## 2. HTTP Request Tracing Middleware
**Files**: `src/langfuse_middleware.py`, `src/coordination_api.py`
**Dependencies**: 1

- [x] 2.1 Implement `LangfuseTracingMiddleware` with per-request trace/span creation
- [x] 2.2 Implement `_resolve_agent_id()` from API key config
- [x] 2.3 Implement `_finalize_trace()` with status-based level assignment
- [x] 2.4 Add error path handling (try/except around `call_next`)
- [x] 2.5 Skip tracing for health/metrics/docs paths
- [x] 2.6 Register middleware conditionally on `get_langfuse()` AND `trace_api_requests` config
- [x] 2.7 Remove per-request flush (rely on SDK batching)

## 3. Claude Code Session Tracing Hook
**Files**: `scripts/langfuse_hook.py`
**Dependencies**: None

- [x] 3.1 Implement transcript discovery (`find_transcript()`)
- [x] 3.2 Implement incremental state management (load/save per session)
- [x] 3.3 Implement `parse_transcript_lines()` returning (messages, lines_consumed)
- [x] 3.4 Implement `group_into_turns()` message grouping
- [x] 3.5 Implement `send_turns_to_langfuse()` with trace + tool-call spans
- [x] 3.6 Implement `sanitize()` with ordered regex patterns for secrets
- [x] 3.7 Advance cursor correctly when turns is empty but lines consumed
- [x] 3.8 Add connection timeout and error handling for Langfuse client creation

## 4. Infrastructure
**Files**: `docker-compose.yml`, `pyproject.toml`, `scripts/setup_langfuse.sh`
**Dependencies**: None

- [x] 4.1 Add Langfuse v3 stack to docker-compose behind `langfuse` profile
- [x] 4.2 Add init container for `langfuse` database creation
- [x] 4.3 Add `langfuse>=3.0,<4.0` to `[observability]` extras
- [x] 4.4 Implement `setup_langfuse.sh` with --local, --cloud, --install-hook modes
- [x] 4.5 Fix cloud mode host override (detect localhost default)

## 5. API Lifecycle Integration
**Files**: `src/coordination_api.py`
**Dependencies**: 1, 2

- [x] 5.1 Call `init_langfuse()` during app startup (before lifespan)
- [x] 5.2 Call `shutdown_langfuse()` during app shutdown (in lifespan cleanup)

## 6. Tests
**Files**: `tests/test_langfuse_tracing.py`, `tests/test_langfuse_middleware.py`, `tests/test_langfuse_hook.py`
**Dependencies**: 1, 2, 3

- [x] 6.1 Test tracing module: disabled, enabled, idempotent, import error, shutdown, trace/span helpers, context manager
- [x] 6.2 Test middleware: skip paths, trace creation, POST tracing, disabled pass-through, agent ID resolution
- [x] 6.3 Test hook: sanitize (API keys, bearer, passwords, Langfuse keys, JWTs, env secrets), turns grouping, transcript parsing, state management
