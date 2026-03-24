"""Tests for the telemetry module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.telemetry import (
    _NoOpSpan,
    get_lock_meter,
    get_policy_meter,
    get_prometheus_app,
    get_queue_meter,
    get_tracer,
    init_telemetry,
    reset_telemetry,
    start_span,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Reset telemetry state before each test."""
    reset_telemetry()
    yield  # type: ignore[misc]
    reset_telemetry()


class TestDisabledByDefault:
    """When OTEL_METRICS_ENABLED and OTEL_TRACES_ENABLED are not set."""

    def test_meters_are_none(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_METRICS_ENABLED", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            init_telemetry()
        assert get_lock_meter() is None
        assert get_queue_meter() is None
        assert get_policy_meter() is None

    def test_tracer_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_METRICS_ENABLED", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            init_telemetry()
        assert get_tracer() is None

    def test_start_span_returns_noop(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_METRICS_ENABLED", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            init_telemetry()
        span = start_span("test.op")
        assert isinstance(span, _NoOpSpan)

    def test_prometheus_app_is_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_METRICS_ENABLED", None)
            os.environ.pop("PROMETHEUS_ENABLED", None)
            init_telemetry()
        assert get_prometheus_app() is None


class TestIdempotentInit:
    """init_telemetry() should be safe to call multiple times."""

    def test_double_init_is_noop(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_METRICS_ENABLED", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            init_telemetry()
            init_telemetry()  # Should not raise
        assert get_lock_meter() is None


class TestNoOpSpan:
    """The no-op span should support the full span interface."""

    def test_context_manager(self) -> None:
        span = _NoOpSpan()
        with span as s:
            assert s is span

    def test_set_attribute(self) -> None:
        span = _NoOpSpan()
        span.set_attribute("key", "value")  # Should not raise

    def test_set_status(self) -> None:
        span = _NoOpSpan()
        span.set_status("ok")  # Should not raise

    def test_record_exception(self) -> None:
        span = _NoOpSpan()
        span.record_exception(ValueError("test"))  # Should not raise


class TestMetricsEnabled:
    """When OTEL_METRICS_ENABLED=true with Prometheus."""

    @pytest.fixture(autouse=True)
    def _env(self) -> None:
        """Set up environment for metrics tests."""
        env = {
            "OTEL_METRICS_ENABLED": "true",
            "PROMETHEUS_ENABLED": "true",
            "OTEL_SERVICE_NAME": "test-coordinator",
        }
        with patch.dict(os.environ, env, clear=False):
            # Remove OTLP endpoint so only Prometheus is used
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            yield  # type: ignore[misc]

    def test_meters_are_created(self) -> None:
        init_telemetry()
        assert get_lock_meter() is not None
        assert get_queue_meter() is not None
        assert get_policy_meter() is not None

    def test_can_create_counter(self) -> None:
        init_telemetry()
        meter = get_lock_meter()
        counter = meter.create_counter("test.counter", unit="1", description="test")
        counter.add(1, {"label": "value"})  # Should not raise

    def test_can_create_histogram(self) -> None:
        init_telemetry()
        meter = get_queue_meter()
        hist = meter.create_histogram("test.histogram", unit="ms", description="test")
        hist.record(42.0, {"label": "value"})  # Should not raise

    def test_can_create_up_down_counter(self) -> None:
        init_telemetry()
        meter = get_lock_meter()
        gauge = meter.create_up_down_counter("test.gauge", unit="1", description="test")
        gauge.add(1)
        gauge.add(-1)  # Should not raise

    def test_prometheus_app_available(self) -> None:
        init_telemetry()
        app = get_prometheus_app()
        assert app is not None


class TestGracefulFallback:
    """When OTel packages are available but configuration is incomplete."""

    def test_metrics_no_exporter_configured(self) -> None:
        """Metrics enabled but no OTLP endpoint and no Prometheus → graceful warning."""
        env = {
            "OTEL_METRICS_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("PROMETHEUS_ENABLED", None)
            os.environ.pop("OTEL_TRACES_ENABLED", None)
            init_telemetry()  # Should not raise
        # Meters stay None when no reader is configured
        assert get_lock_meter() is None
