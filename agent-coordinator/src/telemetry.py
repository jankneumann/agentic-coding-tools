"""OpenTelemetry instrumentation for the Agent Coordinator.

Provides metrics (counters, histograms, gauges) and tracing spans for
lock contention, work queue latency, and policy evaluation.

Disabled by default — enable via OTEL_METRICS_ENABLED=true and/or
OTEL_TRACES_ENABLED=true environment variables.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy OTel imports — only loaded when enabled
# ---------------------------------------------------------------------------

_initialized = False

# Meters (set by init_telemetry or left as None for no-op)
_lock_meter: Any = None
_queue_meter: Any = None
_policy_meter: Any = None

# Tracer
_tracer: Any = None


def _metrics_enabled() -> bool:
    return os.environ.get("OTEL_METRICS_ENABLED", "false").lower() == "true"


def _traces_enabled() -> bool:
    return os.environ.get("OTEL_TRACES_ENABLED", "false").lower() == "true"


def _prometheus_enabled() -> bool:
    return os.environ.get("PROMETHEUS_ENABLED", "false").lower() == "true"


def init_telemetry() -> None:
    """Initialize OpenTelemetry providers based on environment configuration.

    Safe to call multiple times — subsequent calls are no-ops.
    When OTEL_METRICS_ENABLED and OTEL_TRACES_ENABLED are both false,
    this function returns immediately with no side effects.
    """
    global _initialized, _lock_meter, _queue_meter, _policy_meter, _tracer

    if _initialized:
        return
    _initialized = True

    metrics_on = _metrics_enabled()
    traces_on = _traces_enabled()

    if not metrics_on and not traces_on:
        logger.debug("OTel disabled (OTEL_METRICS_ENABLED=false, OTEL_TRACES_ENABLED=false)")
        return

    try:
        if metrics_on:
            _init_metrics()
        if traces_on:
            _init_traces()
    except Exception:
        logger.warning("Failed to initialize OpenTelemetry — falling back to no-ops", exc_info=True)


def _init_metrics() -> None:
    """Set up MeterProvider with OTLP exporter."""
    global _lock_meter, _queue_meter, _policy_meter

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    service_name = os.environ.get("OTEL_SERVICE_NAME", "agent-coordinator")
    resource = Resource.create({"service.name": service_name})

    readers: list[PeriodicExportingMetricReader] = []

    # OTLP exporter
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    export_interval = int(os.environ.get("OTEL_METRICS_EXPORT_INTERVAL_MS", "60000"))

    if endpoint:
        metric_exporter: Any
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter as HttpMetricExporter,
            )

            metric_exporter = HttpMetricExporter(endpoint=endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter as GrpcMetricExporter,
            )

            metric_exporter = GrpcMetricExporter(endpoint=endpoint)

        readers.append(
            PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=export_interval,
            )
        )

    # Prometheus exporter (in-process /metrics endpoint)
    if _prometheus_enabled():
        from opentelemetry.exporter.prometheus import PrometheusMetricReader

        readers.append(PrometheusMetricReader())  # type: ignore[arg-type]

    if not readers:
        # Metrics enabled but no exporter configured — use a no-op reader
        logger.warning(
            "OTEL_METRICS_ENABLED=true but no OTLP endpoint or Prometheus configured"
        )
        return

    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)

    _lock_meter = metrics.get_meter("coordinator.locks", "0.1.0")
    _queue_meter = metrics.get_meter("coordinator.queue", "0.1.0")
    _policy_meter = metrics.get_meter("coordinator.policy", "0.1.0")

    logger.info("OTel metrics initialized (service=%s)", service_name)


def _init_traces() -> None:
    """Set up TracerProvider with OTLP exporter."""
    global _tracer

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.environ.get("OTEL_SERVICE_NAME", "agent-coordinator")
    resource = Resource.create({"service.name": service_name})

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    if not endpoint:
        logger.warning("OTEL_TRACES_ENABLED=true but no OTLP endpoint configured")
        return

    span_exporter: Any
    if protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as HttpSpanExporter,
        )

        span_exporter = HttpSpanExporter(endpoint=endpoint)
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as GrpcSpanExporter,
        )

        span_exporter = GrpcSpanExporter(endpoint=endpoint)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer("coordinator", "0.1.0")

    logger.info("OTel traces initialized (service=%s)", service_name)


# ---------------------------------------------------------------------------
# Public accessor functions — return real instruments or no-op stubs
# ---------------------------------------------------------------------------


def get_lock_meter() -> Any:
    """Return the lock meter, or None if metrics are disabled."""
    return _lock_meter


def get_queue_meter() -> Any:
    """Return the queue meter, or None if metrics are disabled."""
    return _queue_meter


def get_policy_meter() -> Any:
    """Return the policy meter, or None if metrics are disabled."""
    return _policy_meter


def get_tracer() -> Any:
    """Return the tracer, or None if traces are disabled."""
    return _tracer


# ---------------------------------------------------------------------------
# No-op context manager for when tracing is disabled
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Minimal no-op span that supports context manager and set_attribute."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


_NOOP_SPAN = _NoOpSpan()


def start_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Start a tracing span, or return a no-op if tracing is disabled."""
    tracer = get_tracer()
    if tracer is None:
        return _NOOP_SPAN
    return tracer.start_as_current_span(name, attributes=attributes)


# ---------------------------------------------------------------------------
# Prometheus ASGI app for /metrics endpoint
# ---------------------------------------------------------------------------


def get_prometheus_app() -> Any | None:
    """Return the Prometheus ASGI app if enabled, or None.

    Call this after init_telemetry().
    """
    if not _prometheus_enabled() or not _metrics_enabled():
        return None

    try:
        from prometheus_client import REGISTRY, make_asgi_app

        return make_asgi_app(registry=REGISTRY)
    except ImportError:
        logger.warning("prometheus_client not installed — /metrics endpoint unavailable")
        return None


# ---------------------------------------------------------------------------
# Reset for testing
# ---------------------------------------------------------------------------


def reset_telemetry() -> None:
    """Reset all telemetry state. For testing only."""
    global _initialized, _lock_meter, _queue_meter, _policy_meter, _tracer
    _initialized = False
    _lock_meter = None
    _queue_meter = None
    _policy_meter = None
    _tracer = None
