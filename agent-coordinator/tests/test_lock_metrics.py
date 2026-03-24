"""Tests for lock metrics instrumentation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import src.locks as locks_module
from src.locks import LockService, _ensure_instruments
from src.policy_engine import PolicyDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meter_and_reader():
    """Create an in-memory OTel MeterProvider and return (meter, reader)."""
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test.locks")
    return meter, reader, provider


def _get_metric(reader, name: str):
    """Extract a named metric's data points from the in-memory reader."""
    data = reader.get_metrics_data()
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


def _sum_data_points(metric):
    """Sum up the values of all data points in a metric."""
    if metric is None:
        return 0
    pts = metric.data.data_points
    return sum(pt.value for pt in pts)


def _sum_histogram_count(metric):
    """Sum up the count of histogram data points."""
    if metric is None:
        return 0
    return sum(pt.count for pt in metric.data.data_points)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_instruments():
    """Reset cached instruments between tests."""
    locks_module._instruments = None
    yield
    locks_module._instruments = None


@pytest.fixture
def mock_db():
    """Provide a mock DatabaseClient."""
    db = MagicMock()
    db.rpc = AsyncMock()
    return db


@pytest.fixture
def mock_policy():
    """Patch policy engine to always allow."""
    engine = MagicMock()
    engine.check_operation = AsyncMock(
        return_value=PolicyDecision(allowed=True, reason=None)
    )
    with patch("src.policy_engine.get_policy_engine", return_value=engine):
        yield engine


@pytest.fixture
def mock_audit():
    """Patch audit service to no-op."""
    audit = MagicMock()
    audit.log_operation = AsyncMock()
    with patch("src.audit.get_audit_service", return_value=audit):
        yield audit


def _acquired_response():
    expires = datetime.now(UTC) + timedelta(minutes=30)
    return {
        "success": True,
        "action": "acquired",
        "file_path": "src/main.py",
        "expires_at": expires.isoformat(),
    }


def _denied_response():
    return {
        "success": False,
        "reason": "locked_by_other",
        "locked_by": "other-agent",
        "lock_reason": "editing",
    }


def _released_response():
    return {
        "success": True,
        "action": "released",
        "file_path": "src/main.py",
    }


# ---------------------------------------------------------------------------
# Tests — metrics enabled
# ---------------------------------------------------------------------------


class TestLockMetricsEnabled:
    """Verify metrics are recorded when OTel is enabled."""

    @pytest.mark.asyncio
    async def test_acquire_records_duration(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            result = await service.acquire("src/main.py", reason="test")

        assert result.success is True
        m = _get_metric(reader, "lock.acquire.duration_ms")
        assert m is not None
        assert _sum_histogram_count(m) == 1
        provider.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_records_ttl(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            await service.acquire("src/main.py", ttl_minutes=10)

        m = _get_metric(reader, "lock.ttl_seconds")
        assert m is not None
        # 10 minutes * 60 = 600 seconds
        pts = m.data.data_points
        assert any(pt.sum == 600.0 for pt in pts)
        provider.shutdown()

    @pytest.mark.asyncio
    async def test_contention_counter_on_denied(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            mock_db.rpc.return_value = _denied_response()
            service = LockService(mock_db)
            result = await service.acquire("src/main.py")

        assert result.success is False
        m = _get_metric(reader, "lock.contention.total")
        assert m is not None
        assert _sum_data_points(m) == 1
        provider.shutdown()

    @pytest.mark.asyncio
    async def test_active_gauge_increments_on_acquire(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            await service.acquire("src/main.py")

        m = _get_metric(reader, "lock.active")
        assert m is not None
        assert _sum_data_points(m) == 1
        provider.shutdown()

    @pytest.mark.asyncio
    async def test_active_gauge_decrements_on_release(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            # Acquire first
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            await service.acquire("src/main.py")

            # Then release
            mock_db.rpc.return_value = _released_response()
            await service.release("src/main.py")

        m = _get_metric(reader, "lock.active")
        assert m is not None
        # +1 from acquire, -1 from release = 0 net
        assert _sum_data_points(m) == 0
        provider.shutdown()

    @pytest.mark.asyncio
    async def test_duration_labels_include_outcome(self, mock_db, mock_policy, mock_audit):
        meter, reader, provider = _make_meter_and_reader()
        with patch("src.locks.get_lock_meter", return_value=meter):
            mock_db.rpc.return_value = _denied_response()
            service = LockService(mock_db)
            await service.acquire("src/main.py")

        m = _get_metric(reader, "lock.acquire.duration_ms")
        assert m is not None
        pt = m.data.data_points[0]
        attrs = dict(pt.attributes)
        assert attrs["outcome"] == "denied"
        provider.shutdown()


# ---------------------------------------------------------------------------
# Tests — metrics disabled (no meter)
# ---------------------------------------------------------------------------


class TestLockMetricsDisabled:
    """Verify no errors when metrics are disabled (meter is None)."""

    @pytest.mark.asyncio
    async def test_acquire_works_without_metrics(self, mock_db, mock_policy, mock_audit):
        with patch("src.locks.get_lock_meter", return_value=None):
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            result = await service.acquire("src/main.py", reason="test")

        assert result.success is True
        assert result.action == "acquired"

    @pytest.mark.asyncio
    async def test_release_works_without_metrics(self, mock_db, mock_policy, mock_audit):
        with patch("src.locks.get_lock_meter", return_value=None):
            mock_db.rpc.return_value = _released_response()
            service = LockService(mock_db)
            result = await service.release("src/main.py")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_denied_acquire_works_without_metrics(self, mock_db, mock_policy, mock_audit):
        with patch("src.locks.get_lock_meter", return_value=None):
            mock_db.rpc.return_value = _denied_response()
            service = LockService(mock_db)
            result = await service.acquire("src/main.py")

        assert result.success is False

    def test_ensure_instruments_returns_nones_when_disabled(self):
        with patch("src.locks.get_lock_meter", return_value=None):
            instruments = _ensure_instruments()
            assert instruments == (None, None, None, None)


# ---------------------------------------------------------------------------
# Tests — metric recording failure resilience
# ---------------------------------------------------------------------------


class TestLockMetricsResilience:
    """Verify metric failures don't break lock operations."""

    @pytest.mark.asyncio
    async def test_acquire_survives_metric_failure(self, mock_db, mock_policy, mock_audit):
        """If metric recording raises, acquire still returns normally."""
        broken_meter = MagicMock()
        broken_hist = MagicMock()
        broken_hist.record.side_effect = RuntimeError("broken")
        broken_meter.create_histogram.return_value = broken_hist
        broken_meter.create_counter.return_value = MagicMock()
        broken_meter.create_up_down_counter.return_value = MagicMock()

        with patch("src.locks.get_lock_meter", return_value=broken_meter):
            mock_db.rpc.return_value = _acquired_response()
            service = LockService(mock_db)
            result = await service.acquire("src/main.py")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_release_survives_metric_failure(self, mock_db, mock_policy, mock_audit):
        """If metric recording raises, release still returns normally."""
        broken_meter = MagicMock()
        broken_gauge = MagicMock()
        broken_gauge.add.side_effect = RuntimeError("broken")
        broken_meter.create_histogram.return_value = MagicMock()
        broken_meter.create_counter.return_value = MagicMock()
        broken_meter.create_up_down_counter.return_value = broken_gauge

        with patch("src.locks.get_lock_meter", return_value=broken_meter):
            mock_db.rpc.return_value = _released_response()
            service = LockService(mock_db)
            result = await service.release("src/main.py")

        assert result.success is True
