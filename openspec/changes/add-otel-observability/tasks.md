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

- [ ] T1.1: Add `opentelemetry-*` packages to `pyproject.toml` under `[observability]` extras
- [ ] T1.2: Create `src/telemetry.py` with `init_telemetry()`, named meters, tracer provider
- [ ] T1.3: Add OTel config fields to `src/config.py` (`ObservabilityConfig` dataclass)
- [ ] T1.4: Wire `init_telemetry()` into MCP server startup (`coordination_mcp.py`)
- [ ] T1.5: Wire `init_telemetry()` into HTTP API startup (`coordination_api.py`)
- [ ] T1.6: Add Prometheus exporter and `/metrics` route to HTTP API
- [ ] T1.7: Write unit tests for telemetry module (init, no-op, config parsing)

### T2: Lock Contention Metrics (`wp-lock-metrics`)

- [ ] T2.1: Add duration histogram to `LockService.acquire()`
- [ ] T2.2: Add contention counter (denied acquisitions)
- [ ] T2.3: Add active lock UpDownCounter on acquire/release
- [ ] T2.4: Add TTL histogram
- [ ] T2.5: Add tracing spans to acquire/release
- [ ] T2.6: Write unit tests with in-memory exporter

### T3: Queue Latency Metrics (`wp-queue-metrics`)

- [ ] T3.1: Add claim duration histogram to `WorkQueueService.claim()`
- [ ] T3.2: Add wait time histogram (created_at → claimed_at)
- [ ] T3.3: Add task duration histogram to `WorkQueueService.complete()`
- [ ] T3.4: Add submit counter to `WorkQueueService.submit()`
- [ ] T3.5: Add guardrail block counter
- [ ] T3.6: Add tracing spans to claim/complete/submit
- [ ] T3.7: Write unit tests with in-memory exporter

### T4: Policy Evaluation Metrics (`wp-policy-metrics`)

- [ ] T4.1: Add evaluation duration histogram to both NativePolicyEngine and CedarPolicyEngine
- [ ] T4.2: Add decision counter (allow/deny by engine and operation)
- [ ] T4.3: Add Cedar cache hit/miss counter
- [ ] T4.4: Add guardrail check duration histogram
- [ ] T4.5: Add violation counter by pattern and severity
- [ ] T4.6: Add tracing spans to policy evaluate and guardrail check
- [ ] T4.7: Write unit tests with in-memory exporter

### T5: Integration and Validation (`wp-integration`)

- [ ] T5.1: Integration test: metrics flow end-to-end with OTLP in-memory collector
- [ ] T5.2: Integration test: `/metrics` Prometheus endpoint returns expected format
- [ ] T5.3: Verify existing tests pass with OTel disabled (no-op)
- [ ] T5.4: Verify existing tests pass with OTel enabled (in-memory exporter)
- [ ] T5.5: Update CI workflow to install `[observability]` extras
- [ ] T5.6: Run `mypy --strict` and `ruff check` on all new/modified files
