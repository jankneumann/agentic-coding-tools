# Proposal: Add Langfuse Observability

**Change ID**: `add-langfuse-observability`
**Status**: Implemented
**Author**: Claude Code
**Date**: 2026-04-04

## Why

The existing observability spec covers operational metrics (lock contention, queue latency, policy evaluation) via OpenTelemetry and Prometheus. However, there is no **session-level tracing** that connects coding agent conversations to coordinator operations. When debugging why an agent made certain coordination calls, operators must manually correlate Claude Code transcripts with coordinator logs.

Langfuse provides purpose-built LLM observability: traces, spans, session grouping, and a UI for inspecting conversation flows. Adding Langfuse integration creates a unified timeline where both local agent sessions (via a Claude Code Stop hook) and cloud agent API calls (via FastAPI middleware) appear as traces within the same Langfuse project.

## What Changes

Add cross-agent session tracing via Langfuse with two complementary mechanisms:

1. **Claude Code Stop hook** (`scripts/langfuse_hook.py`) — Runs after each assistant response, reads the session transcript incrementally, and sends conversation turns to Langfuse as traces with nested tool-call spans. Sanitizes secrets before sending.

2. **FastAPI middleware** (`src/langfuse_middleware.py`) — Traces coordinator HTTP API requests server-side, capturing agent identity, operation name, timing, and status codes. This covers cloud agents (Codex, Gemini) that don't run Claude Code locally.

3. **Core tracing module** (`src/langfuse_tracing.py`) — Lazy-initialized Langfuse client with helpers for creating traces, spans, and a `trace_operation` context manager. Disabled by default (`LANGFUSE_ENABLED=false`).

4. **Self-hosted stack** (`docker-compose.yml` langfuse profile) — Langfuse v3 with ClickHouse, Redis, MinIO, reusing the existing Postgres instance.

5. **Setup script** (`scripts/setup_langfuse.sh`) — Configures local or cloud Langfuse, installs the Claude Code hook.

### Integration with Existing Observability

- Langfuse runs alongside (not replacing) the existing OpenTelemetry/Prometheus stack
- The `langfuse` dependency is in the `[observability]` extras group alongside OTel packages
- Langfuse is fully disabled by default — zero overhead when not configured
- The middleware registration respects `LANGFUSE_TRACE_API_REQUESTS` config toggle

## Impact

- **New files**: 5 source files, 3 test files, 1 setup script
- **Modified files**: `config.py` (LangfuseConfig dataclass), `coordination_api.py` (middleware + lifespan), `docker-compose.yml` (langfuse profile), `pyproject.toml` (langfuse dependency)
- **No breaking changes**: Feature is opt-in, disabled by default
- **Test coverage**: 43 unit tests covering tracing, middleware, hook, and sanitization
