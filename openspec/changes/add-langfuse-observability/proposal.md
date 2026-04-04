# Change: add-langfuse-observability

## Why

The agent-coordinator has OpenTelemetry instrumentation for infrastructure metrics (lock contention, queue latency, policy evaluation), but no visibility into the **AI coding session layer** — what prompts were sent, which tools were invoked, how long each turn took, or how coding agent sessions correlate with coordinator operations. When debugging a multi-agent coding session, operators must piece together fragmented logs across multiple agents with no unified timeline.

Langfuse provides LLM-specific observability — traces, generations, and session grouping — that complements OpenTelemetry's infrastructure focus. The agentic-newsletter-aggregator project already uses Langfuse successfully, proving the pattern. Adding it to the coding agent stack gives operators a single pane of glass across both local agents (Claude Code) and cloud agents (Codex, Gemini) interacting with the coordinator.

## What Changes

### Phase 1 (Implemented)
- Add **Langfuse v3 self-hosted stack** to `docker-compose.yml` under `--profile langfuse`, reusing the existing ParadeDB Postgres instance with a separate `langfuse` database
- Add **`langfuse_tracing.py`** module to agent-coordinator: lazy-initialized Langfuse client with trace/span helpers and a `trace_operation` context manager
- Add **`langfuse_middleware.py`** FastAPI middleware that traces all coordinator HTTP API requests, providing **cloud agent observability** server-side (since cloud agents can't run local hooks)
- Add **`langfuse_hook.py`** Claude Code Stop hook that parses `transcript.jsonl` and sends conversation turns with tool call spans to Langfuse for **local agent observability**
- Add **`setup_langfuse.sh`** setup script supporting local, cloud, and BYOL (bring-your-own-Langfuse) deployment
- Add **`LangfuseConfig`** dataclass to `config.py` with environment variable control (`LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, etc.)
- Add **`langfuse>=3.0,<4.0`** to `[observability]` optional dependency group
- Add **40 unit tests** covering tracing module, middleware, and hook parsing

### Phase 2 (Future Roadmap)
- **Offline resilience queue**: Serialize traces to disk when Langfuse is unreachable, drain on reconnect
- **Permission governance integration**: Read `~/.claude/logs/permission-events.jsonl` and attach as trace metadata
- **Token estimation and cost tracking**: Estimate token counts per turn and report as Langfuse generation metadata
- **MCP tool-level tracing**: Instrument individual MCP tool invocations in the coordinator as Langfuse spans (not just HTTP API requests)
- **Multi-session correlation**: Link coordinator traces to coding agent session traces via shared trace IDs

## Approaches Considered

### Approach 1: Langfuse SDK Direct Integration

Add the Langfuse Python SDK (`langfuse>=3.0`) as a direct dependency of the coordinator. Create a `langfuse_tracing.py` module mirroring the existing `telemetry.py` pattern (lazy init, env-var gating, no-op fallback). For local agents, use a Claude Code Stop hook that parses transcript JSONL. For cloud agents, add FastAPI middleware that traces API requests server-side.

- **Pros**: Rich Langfuse-native features (generations, scores, session grouping), straightforward integration following existing `telemetry.py` patterns, unified session view across agent types
- **Cons**: Adds a vendor-specific dependency alongside the vendor-neutral OTel stack, two observability systems to maintain
- **Effort**: M

### Approach 2: OpenTelemetry GenAI via OTLP Bridge

Use OTel GenAI semantic conventions (`gen_ai.*` attributes) as the sole instrumentation layer. Configure Langfuse as an OTLP-compatible backend receiving traces at `/api/public/otel/v1/traces`. Spans with `gen_ai.operation.name` automatically become Langfuse generations. Session grouping via `langfuse.trace.session_id` attribute. No Langfuse SDK needed in coordinator code; hook still uses OTel SDK + OTLP HTTP exporter.

- **Pros**: Vendor-neutral instrumentation, leverages existing OTel investment, single SDK for both infrastructure and LLM tracing, future-proof if OTel GenAI conventions stabilize
- **Cons**: OTel GenAI conventions still experimental, Langfuse OTLP path has known bugs (#11135 token mapping, #11030 cost_details), session grouping requires `langfuse.*` attributes anyway (partial vendor coupling), no access to Langfuse scoring/prompt management
- **Effort**: M

### Approach 3: Coordinator-Only Tracing (No Hook)

Add Langfuse SDK to the coordinator only. All agent observability flows through coordinator API calls. Skip the Claude Code Stop hook entirely — local agents are observed via their coordinator interactions.

- **Pros**: Simpler architecture (one integration point), no client-side hook management
- **Cons**: Loses visibility into local agent tool calls, conversation turns, and prompt/response content. Only sees coordinator API interactions, which are a small subset of agent activity
- **Effort**: S

### Recommended

**Approach 1** (Langfuse SDK Direct Integration). The Stop hook + middleware combination provides the richest observability: local agents get full conversation tracing including tool calls, while cloud agents get server-side API tracing. Approach 2 loses critical Langfuse features (session grouping, generations), and Approach 3 has a major blind spot for local agent activity. The dual-SDK pattern (OTel for infrastructure, Langfuse for LLM sessions) is a proven pattern in AI-native stacks.

### Selected Approach

**Approach 1** (Langfuse SDK Direct Integration) selected. The OTel GenAI OTLP path (Approach 2) was investigated in depth — Langfuse accepts OTLP natively since v3.22.0 and GenAI conventions cover sessions, generations, and token counts. However, the OTLP integration still has known bugs (Langfuse issues #11135, #11030), GenAI conventions are still experimental, and session grouping requires `langfuse.*` attributes regardless (partial vendor coupling). The Langfuse SDK provides the most mature and feature-complete integration today, with a clear migration path to OTel GenAI conventions in the future if desired.

Approach 3 (Coordinator-Only) was rejected due to the critical blind spot for local agent activity (no visibility into conversation turns, tool calls, or prompt content for Claude Code sessions).

## Impact

- **Affected specs**: `observability` (extend with Langfuse requirements)
- **Files modified**:
  - `agent-coordinator/src/langfuse_tracing.py` — New: coordinator Langfuse client module
  - `agent-coordinator/src/langfuse_middleware.py` — New: FastAPI request tracing middleware
  - `agent-coordinator/src/config.py` — Add `LangfuseConfig` dataclass
  - `agent-coordinator/src/coordination_api.py` — Wire Langfuse lifecycle + middleware
  - `agent-coordinator/scripts/langfuse_hook.py` — New: Claude Code Stop hook
  - `agent-coordinator/scripts/setup_langfuse.sh` — New: setup/install script
  - `agent-coordinator/docker-compose.yml` — Add Langfuse stack under `langfuse` profile
  - `agent-coordinator/pyproject.toml` — Add `langfuse>=3.0,<4.0` to observability extras
  - `agent-coordinator/tests/test_langfuse_*.py` — New: 40 unit tests
- **Docker**: New services under `--profile langfuse` (langfuse-web, langfuse-worker, ClickHouse, Redis, MinIO)
- **Deployment**: Self-hosted primary path with cloud/BYOL as documented alternatives
