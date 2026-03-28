## ADDED Requirements

### Requirement: Telemetry Module and Configuration

The coordinator SHALL provide a `telemetry` module that initializes OpenTelemetry MeterProvider and TracerProvider based on environment configuration, with zero overhead when disabled.

- The telemetry module SHALL expose named meters: `coordinator.locks`, `coordinator.queue`, `coordinator.policy`
- When `OTEL_METRICS_ENABLED` is not `true`, all metric instruments SHALL be no-ops with zero measurable overhead
- OTel dependencies MUST be in an optional extras group (`[observability]`) to avoid bloating the core install
- The `init_telemetry()` function SHALL be called during MCP server and HTTP API startup

#### Scenario: Telemetry enabled with OTLP exporter
- **WHEN** `OTEL_METRICS_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
- **THEN** system initializes MeterProvider with OTLP exporter
- **AND** named meters `coordinator.locks`, `coordinator.queue`, `coordinator.policy` are available
- **AND** metric instruments record values to the configured exporter

#### Scenario: Telemetry disabled (default)
- **WHEN** `OTEL_METRICS_ENABLED` is not set or is `false`
- **THEN** system initializes no-op MeterProvider
- **AND** all metric record calls are zero-cost no-ops
- **AND** no network connections are established to any exporter

---

### Requirement: Lock Contention Metrics

`LockService` SHALL emit OpenTelemetry metrics and traces for lock acquisition, contention, and lifecycle tracking.

- `LockService.acquire()` SHALL record a histogram `lock.acquire.duration_ms` with labels `outcome` and `agent_type`
- `LockService.acquire()` SHALL increment `lock.contention.total` when a lock request is denied due to an existing holder
- `LockService.acquire()` and `release()` SHALL maintain an UpDownCounter `lock.active` tracking currently held locks
- `LockService.acquire()` SHALL create a tracing span `lock.acquire` with structured attributes

#### Scenario: Successful lock acquisition records metrics
- **WHEN** agent `claude-code-1` of type `claude_code` acquires lock on `src/api/users.py`
- **THEN** `lock.acquire.duration_ms` histogram records the RPC duration with `outcome=acquired`, `agent_type=claude_code`
- **AND** `lock.active` UpDownCounter increments by 1

#### Scenario: Lock contention recorded
- **WHEN** agent `codex-1` attempts to acquire lock on `src/api/users.py` already held by `claude-code-1`
- **THEN** `lock.contention.total` counter increments with `holder_type=claude_code`, `requester_type=codex`
- **AND** `lock.acquire.duration_ms` histogram records with `outcome=denied`

#### Scenario: Lock release decrements active gauge
- **WHEN** agent releases lock on `src/api/users.py`
- **THEN** `lock.active` UpDownCounter decrements by 1

---

### Requirement: Queue Latency Metrics

`WorkQueueService` SHALL emit OpenTelemetry metrics and traces for task lifecycle latency, submission rates, and guardrail blocks.

- `WorkQueueService.claim()` SHALL record `queue.claim.duration_ms` with labels `task_type` and `outcome`
- `WorkQueueService.claim()` SHALL record `queue.wait_time_ms` (time from task creation to claim) when a task is successfully claimed
- `WorkQueueService.complete()` SHALL record `queue.task.duration_ms` (time from claim to completion) with labels `task_type` and `outcome`
- `WorkQueueService.submit()` SHALL increment `queue.submit.total` with label `task_type`
- `WorkQueueService.claim()` SHALL increment `queue.guardrail_block.total` when a guardrail check blocks task execution

#### Scenario: Task claimed with wait time
- **WHEN** task of type `verify` submitted at T0 is claimed at T1 by agent
- **THEN** `queue.claim.duration_ms` histogram records RPC duration with `task_type=verify`, `outcome=claimed`
- **AND** `queue.wait_time_ms` histogram records `T1 - T0` in milliseconds with `task_type=verify`

#### Scenario: Task completion records duration
- **WHEN** agent completes task claimed at T1, completing at T2 with success
- **THEN** `queue.task.duration_ms` histogram records `T2 - T1` with `task_type=verify`, `outcome=completed`

#### Scenario: Guardrail blocks task execution
- **WHEN** claimed task description matches guardrail pattern `rm_rf`
- **THEN** `queue.guardrail_block.total` counter increments with `pattern=rm_rf`
- **AND** task is auto-released with failure

---

### Requirement: Policy Evaluation Metrics

`PolicyEngine` and `GuardrailsService` SHALL emit OpenTelemetry metrics and traces for evaluation latency, decision outcomes, cache performance, and violation detection.

- `PolicyEngine.check_operation()` SHALL record `policy.evaluate.duration_ms` with labels `engine`, `operation`, and `decision`
- `CedarPolicyEngine._load_policies()` SHALL track `policy.cache.total` with label `result` in {`hit`, `miss`}
- `GuardrailsService.check_operation()` SHALL record `guardrail.check.duration_ms` and increment `guardrail.violation.total` per detected pattern
- Policy evaluation SHALL create tracing spans `policy.evaluate` and `guardrail.check`

#### Scenario: Native policy evaluation recorded
- **WHEN** native policy engine evaluates `acquire_lock` operation for agent with trust level 2
- **THEN** `policy.evaluate.duration_ms` histogram records with `engine=native`, `operation=acquire_lock`, `decision=allow`
- **AND** `policy.decision.total` counter increments with same labels

#### Scenario: Cedar policy cache hit
- **WHEN** CedarPolicyEngine evaluates an operation and cached policies are within TTL
- **THEN** `policy.cache.total` counter increments with `result=hit`
- **AND** no database query is made to load policies

#### Scenario: Guardrail violation detected
- **WHEN** guardrail check detects `force_push` pattern with `severity=block`
- **THEN** `guardrail.violation.total` counter increments with `pattern=force_push`, `severity=block`
- **AND** `guardrail.check.duration_ms` histogram records the check duration

---

### Requirement: Prometheus Metrics Endpoint

When enabled, the HTTP API SHALL expose a `/metrics` endpoint returning Prometheus text format metrics.

- When `PROMETHEUS_ENABLED=true`, the HTTP API SHALL expose a `/metrics` endpoint
- The `/metrics` endpoint SHALL NOT require authentication
- The `/metrics` endpoint MUST NOT expose sensitive data (agent IDs, file paths, task descriptions)

#### Scenario: Prometheus endpoint returns metrics
- **WHEN** `PROMETHEUS_ENABLED=true` and coordinator has processed operations
- **THEN** `GET /metrics` returns HTTP 200 with `Content-Type: text/plain`
- **AND** response contains `lock_acquire_duration_ms`, `queue_claim_duration_ms`, `policy_evaluate_duration_ms` metric families

#### Scenario: Prometheus endpoint disabled by default
- **WHEN** `PROMETHEUS_ENABLED` is not set
- **THEN** `GET /metrics` returns HTTP 404
