# Tasks: add-langfuse-observability

## Phase 1: Core Langfuse Integration (Implemented)

### 1. Configuration and Dependencies

- [x] 1.1 Write tests for LangfuseConfig dataclass
  **Spec scenarios**: observability.langfuse-config (enabled, disabled, SDK missing)
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/test_langfuse_tracing.py`

- [x] 1.2 Add `LangfuseConfig` dataclass to `config.py` with env var control
  **Dependencies**: 1.1
  **Files**: `agent-coordinator/src/config.py`

- [x] 1.3 Add `langfuse>=3.0,<4.0` to `[observability]` optional extras group
  **Dependencies**: None
  **Files**: `agent-coordinator/pyproject.toml`

### 2. Coordinator Langfuse Tracing Module

- [x] 2.1 Write tests for langfuse_tracing module (init, shutdown, create_trace, create_span, trace_operation)
  **Spec scenarios**: observability.langfuse-config (enabled, disabled, SDK missing), observability.langfuse-module (trace creation, span creation, error recording)
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/tests/test_langfuse_tracing.py`

- [x] 2.2 Create `langfuse_tracing.py` — lazy-init client, trace/span helpers, trace_operation context manager
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/src/langfuse_tracing.py`

### 3. FastAPI Middleware for Cloud Agent Observability

- [x] 3.1 Write tests for LangfuseTracingMiddleware (skip paths, tracing, disabled pass-through, agent ID resolution)
  **Spec scenarios**: observability.middleware (cloud agent traced, session grouping, health excluded, error level)
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/tests/test_langfuse_middleware.py`

- [x] 3.2 Create `langfuse_middleware.py` — FastAPI middleware tracing API requests with agent identity resolution
  **Dependencies**: 3.1
  **Files**: `agent-coordinator/src/langfuse_middleware.py`

- [x] 3.3 Wire Langfuse lifecycle (init/shutdown) and middleware into `coordination_api.py`
  **Dependencies**: 3.2
  **Files**: `agent-coordinator/src/coordination_api.py`

### 4. Claude Code Stop Hook

- [x] 4.1 Write tests for hook parsing logic (sanitize, group_into_turns, extract_text, truncate, state management)
  **Spec scenarios**: observability.hook (single turn, incremental, secret redaction, disabled)
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/test_langfuse_hook.py`

- [x] 4.2 Create `langfuse_hook.py` — transcript parser, turn grouper, Langfuse trace sender
  **Dependencies**: 4.1
  **Files**: `agent-coordinator/scripts/langfuse_hook.py`

### 5. Docker Infrastructure

- [x] 5.1 Add Langfuse v3 services to docker-compose.yml under `langfuse` profile
  **Spec scenarios**: observability.infra (stack starts with profile, not without, Postgres preserved)
  **Dependencies**: None
  **Files**: `agent-coordinator/docker-compose.yml`

### 6. Setup Script

- [x] 6.1 Create `setup_langfuse.sh` with local/cloud/install-hook/check modes
  **Spec scenarios**: observability.setup (local setup, health check)
  **Dependencies**: 4.2, 5.1
  **Files**: `agent-coordinator/scripts/setup_langfuse.sh`

## Phase 2: Enhanced Observability (Future Roadmap)

### 7. Offline Resilience Queue

- [ ] 7.1 Write tests for offline trace queue (serialize, drain, partial drain recovery)
  **Spec scenarios**: TBD (Phase 2 spec extension)
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/tests/test_langfuse_hook.py`

- [ ] 7.2 Add socket-level health check to hook before Langfuse connection
  **Dependencies**: 7.1
  **Files**: `agent-coordinator/scripts/langfuse_hook.py`

- [ ] 7.3 Implement pending_traces.jsonl queue with drain-on-reconnect logic
  **Dependencies**: 7.2
  **Files**: `agent-coordinator/scripts/langfuse_hook.py`

### 8. Permission Governance Integration

- [ ] 8.1 Write tests for permission event parsing and trace metadata attachment
  **Spec scenarios**: TBD (Phase 2 spec extension)
  **Dependencies**: 4.2
  **Files**: `agent-coordinator/tests/test_langfuse_hook.py`

- [ ] 8.2 Read `~/.claude/logs/permission-events.jsonl` and attach as trace spans
  **Dependencies**: 8.1
  **Files**: `agent-coordinator/scripts/langfuse_hook.py`

### 9. Token Estimation and Cost Tracking

- [ ] 9.1 Write tests for token estimation and Langfuse generation metadata
  **Spec scenarios**: TBD (Phase 2 spec extension)
  **Dependencies**: 4.2
  **Files**: `agent-coordinator/tests/test_langfuse_hook.py`

- [ ] 9.2 Add token count estimation per turn and report as Langfuse generation observations
  **Dependencies**: 9.1
  **Files**: `agent-coordinator/scripts/langfuse_hook.py`

### 10. MCP Tool-Level Tracing

- [ ] 10.1 Write tests for MCP tool invocation tracing
  **Spec scenarios**: TBD (Phase 2 spec extension)
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/tests/test_langfuse_tracing.py`

- [ ] 10.2 Instrument MCP tool handler in `coordination_mcp.py` with Langfuse spans
  **Dependencies**: 10.1
  **Files**: `agent-coordinator/src/coordination_mcp.py`

### 11. Multi-Session Correlation

- [ ] 11.1 Design trace ID propagation scheme between hook and coordinator middleware
  **Spec scenarios**: TBD (Phase 2 spec extension)
  **Dependencies**: 3.2, 4.2

- [ ] 11.2 Implement shared trace ID via X-Trace-Id header or session-based linking
  **Dependencies**: 11.1
  **Files**: `agent-coordinator/src/langfuse_middleware.py`, `agent-coordinator/scripts/langfuse_hook.py`
