# Tasks: Add OpenTelemetry Observability Metrics

## Task Dependency Graph

```
wp-otel-core ──┬── wp-lock-metrics
               ├── wp-queue-metrics
               ├── wp-policy-metrics
               └───────┴────┴────── wp-integration
```

## Tasks

### T1: Core OTel Infrastructure (`wp-otel-core`)

- [x] T1.1: Add `opentelemetry-*` packages to `pyproject.toml` under `[observability]` extras
- [x] T1.2: Create `src/telemetry.py` with `init_telemetry()`, named meters, tracer provider
- [x] T1.3: Add OTel config fields to `src/config.py` (`ObservabilityConfig` dataclass)
- [x] T1.4: Wire `init_telemetry()` into MCP server startup (`coordination_mcp.py`)
- [x] T1.5: Wire `init_telemetry()` into HTTP API startup (`coordination_api.py`)
- [x] T1.6: Add Prometheus exporter and `/metrics` route to HTTP API
- [x] T1.7: Write unit tests for telemetry module (init, no-op, config parsing)

### T2: Lock Contention Metrics (`wp-lock-metrics`)

- [x] T2.1: Add duration histogram to `LockService.acquire()`
- [x] T2.2: Add contention counter (denied acquisitions)
- [x] T2.3: Add active lock UpDownCounter on acquire/release
- [x] T2.4: Add TTL histogram
- [x] T2.5: Add tracing spans to acquire/release
- [x] T2.6: Write unit tests with in-memory exporter

### T3: Queue Latency Metrics (`wp-queue-metrics`)

- [x] T3.1: Add claim duration histogram to `WorkQueueService.claim()`
- [x] T3.2: Add wait time histogram (created_at → claimed_at)
- [x] T3.3: Add task duration histogram to `WorkQueueService.complete()`
- [x] T3.4: Add submit counter to `WorkQueueService.submit()`
- [x] T3.5: Add guardrail block counter
- [x] T3.6: Add tracing spans to claim/complete/submit
- [x] T3.7: Write unit tests with in-memory exporter

### T4: Policy Evaluation Metrics (`wp-policy-metrics`)

- [x] T4.1: Add evaluation duration histogram to both NativePolicyEngine and CedarPolicyEngine
- [x] T4.2: Add decision counter (allow/deny by engine and operation)
- [x] T4.3: Add Cedar cache hit/miss counter
- [x] T4.4: Add guardrail check duration histogram
- [x] T4.5: Add violation counter by pattern and severity
- [x] T4.6: Add tracing spans to policy evaluate and guardrail check
- [x] T4.7: Write unit tests with in-memory exporter

### T5: Integration and Validation (`wp-integration`)

- [ ] T5.1: Integration test: metrics flow end-to-end with OTLP in-memory collector
- [ ] T5.2: Integration test: `/metrics` Prometheus endpoint returns expected format
- [x] T5.3: Verify existing tests pass with OTel disabled (no-op)
- [x] T5.4: Verify existing tests pass with OTel enabled (in-memory exporter)
- [x] T5.5: Update CI workflow to install `[observability]` extras
- [x] T5.6: Run `mypy --strict` and `ruff check` on all new/modified files
