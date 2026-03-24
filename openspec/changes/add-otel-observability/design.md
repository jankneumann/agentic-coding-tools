# Design: OpenTelemetry Observability Metrics

## Architecture Decision

### OTel SDK vs Custom Metrics

**Decision**: Use the official OpenTelemetry Python SDK.

**Rationale**: OTel is the CNCF standard for observability. It provides vendor-neutral instrumentation, pluggable exporters, and zero-cost no-op fallbacks when disabled. Rolling our own would duplicate the ecosystem and lock us into a proprietary format.

### Instrumentation Approach

**Decision**: Service-layer decoration (not middleware).

Each service (`LockService`, `WorkQueueService`, `PolicyEngine`) gets instrumented at the method level. This gives us fine-grained control over metric labels (agent_id, operation type, outcome) without coupling to transport (MCP vs HTTP).

```
MCP/HTTP entry → Service method → [OTel span + metrics] → DB RPC → [OTel span]
```

### Module Structure

A new `telemetry.py` module in `agent-coordinator/src/` provides:
1. `init_telemetry()` — Configure MeterProvider, TracerProvider, exporters based on env vars
2. Named meters per subsystem: `coordinator.locks`, `coordinator.queue`, `coordinator.policy`
3. Helper to get no-op instruments when disabled (zero overhead)

### Configuration

Follow OTel SDK conventions plus coordinator-specific vars:

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_METRICS_ENABLED` | `false` | Master switch for metrics |
| `OTEL_TRACES_ENABLED` | `false` | Master switch for traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | `grpc` or `http/protobuf` |
| `OTEL_SERVICE_NAME` | `agent-coordinator` | Service name tag |
| `OTEL_METRICS_EXPORT_INTERVAL_MS` | `60000` | Export interval |
| `PROMETHEUS_ENABLED` | `false` | Enable `/metrics` endpoint |

### Metric Definitions

#### Lock Contention (`coordinator.locks`)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `lock.acquire.duration_ms` | Histogram | `outcome`, `agent_type` | Time to acquire (including DB round-trip) |
| `lock.acquire.total` | Counter | `outcome`, `agent_type` | Total acquisition attempts |
| `lock.contention.total` | Counter | `holder_type`, `requester_type` | Failed acquires due to existing holder |
| `lock.active` | UpDownCounter | `agent_type` | Currently held locks |
| `lock.ttl_seconds` | Histogram | `agent_type` | TTL values requested |

`outcome` ∈ {`acquired`, `refreshed`, `denied`, `error`}

#### Queue Latency (`coordinator.queue`)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `queue.claim.duration_ms` | Histogram | `task_type`, `outcome` | Time to claim a task |
| `queue.wait_time_ms` | Histogram | `task_type`, `priority` | Time from submit to claim |
| `queue.task.duration_ms` | Histogram | `task_type`, `outcome` | Time from claim to completion |
| `queue.pending` | Gauge (async) | `task_type`, `priority` | Current pending tasks |
| `queue.submit.total` | Counter | `task_type` | Total submissions |
| `queue.guardrail_block.total` | Counter | `pattern` | Tasks blocked by guardrails |

`outcome` ∈ {`claimed`, `empty`, `error`} for claims; {`completed`, `failed`} for tasks

#### Policy Evaluation (`coordinator.policy`)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `policy.evaluate.duration_ms` | Histogram | `engine`, `operation`, `decision` | Evaluation latency |
| `policy.decision.total` | Counter | `engine`, `operation`, `decision` | Decision outcomes |
| `policy.cache.total` | Counter | `result` | Cedar policy cache hits/misses |
| `policy.trust_level` | Histogram | `agent_type` | Trust levels evaluated |
| `guardrail.check.duration_ms` | Histogram | `outcome` | Guardrail check latency |
| `guardrail.violation.total` | Counter | `pattern`, `severity` | Violations detected |

`decision` ∈ {`allow`, `deny`}; `result` ∈ {`hit`, `miss`}

### Tracing Spans

Each instrumented service method creates a span:
- `lock.acquire`, `lock.release`
- `queue.claim`, `queue.complete`, `queue.submit`
- `policy.evaluate`, `guardrail.check`

Spans include structured attributes (agent_id, resource, outcome) for filtering.

## Alternatives Considered

### 1. Prometheus client library directly

**Rejected**: Prometheus-only lock-in. OTel's Prometheus exporter gives us the same `/metrics` endpoint while supporting OTLP for Datadog, Honeycomb, etc.

### 2. StatsD / custom UDP metrics

**Rejected**: No tracing support, limited label cardinality, non-standard.

### 3. Extend audit_log with computed metrics views

**Rejected**: Audit log is write-optimized and append-only. Real-time metric queries on it would degrade write performance and mix concerns.

## Risks

| Risk | Mitigation |
|------|------------|
| OTel SDK adds startup latency | Lazy initialization; disabled by default |
| Histogram cardinality explosion | Bounded label sets; no per-file or per-agent-id labels on histograms |
| `asyncpg` + OTel context propagation conflicts | Use `opentelemetry-instrumentation-asyncpg` only if needed; start with manual spans |
| CI dependency bloat | OTel packages in optional `[observability]` extras group |

## Dependencies

New packages (all in optional `[observability]` extras):
- `opentelemetry-api>=1.20.0`
- `opentelemetry-sdk>=1.20.0`
- `opentelemetry-exporter-otlp>=1.20.0`
- `opentelemetry-exporter-prometheus>=0.45b0` (for `/metrics` endpoint)
