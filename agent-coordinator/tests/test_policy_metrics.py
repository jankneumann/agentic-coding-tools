"""Tests for OpenTelemetry metrics instrumentation in policy_engine and guardrails."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.guardrails import (
    GuardrailsService,
    reset_guardrail_instruments,
)
from src.policy_engine import (
    NativePolicyEngine,
    reset_policy_instruments,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_instruments():
    """Reset cached metric instruments before and after each test."""
    reset_policy_instruments()
    reset_guardrail_instruments()
    yield
    reset_policy_instruments()
    reset_guardrail_instruments()


def _make_mock_meter() -> MagicMock:
    """Return a mock OTel Meter with create_histogram / create_counter."""
    meter = MagicMock()
    meter.create_histogram.return_value = MagicMock()
    meter.create_counter.return_value = MagicMock()
    return meter


# ---------------------------------------------------------------------------
# NativePolicyEngine metric tests
# ---------------------------------------------------------------------------


class TestNativePolicyEngineMetrics:
    """Verify NativePolicyEngine records OTel metrics."""

    @pytest.mark.asyncio
    async def test_records_duration_and_decision(self, mock_supabase, db_client):
        """Duration histogram and decision counter should be called."""
        mock_meter = _make_mock_meter()
        hist = MagicMock()
        counter = MagicMock()
        cache_counter = MagicMock()
        mock_meter.create_histogram.return_value = hist
        mock_meter.create_counter.side_effect = [counter, cache_counter]

        with patch("src.policy_engine.get_policy_meter", return_value=mock_meter):
            engine = NativePolicyEngine(db_client)
            result = await engine.check_operation(
                agent_id="a1",
                agent_type="claude_code",
                operation="check_locks",
                context={"trust_level": 1},
            )

        assert result.allowed is True
        # Histogram should have been recorded once
        hist.record.assert_called_once()
        args, kwargs = hist.record.call_args
        assert args[0] >= 0  # duration_ms >= 0
        labels = args[1]
        assert labels["engine"] == "native"
        assert labels["operation"] == "check_locks"
        assert labels["decision"] == "allow"

        # Decision counter
        counter.add.assert_called_once()
        cargs, _ = counter.add.call_args
        assert cargs[0] == 1
        assert cargs[1]["decision"] == "allow"

    @pytest.mark.asyncio
    async def test_deny_records_deny_label(self, mock_supabase, db_client):
        """Denied operations should record decision='deny'."""
        mock_meter = _make_mock_meter()
        hist = MagicMock()
        counter = MagicMock()
        cache_counter = MagicMock()
        mock_meter.create_histogram.return_value = hist
        mock_meter.create_counter.side_effect = [counter, cache_counter]

        with patch("src.policy_engine.get_policy_meter", return_value=mock_meter):
            engine = NativePolicyEngine(db_client)
            result = await engine.check_operation(
                agent_id="a1",
                agent_type="claude_code",
                operation="acquire_lock",
                context={"trust_level": 1},
            )

        assert result.allowed is False
        labels = hist.record.call_args[0][1]
        assert labels["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_no_metrics_when_disabled(self, mock_supabase, db_client):
        """When meter is None, no metrics are recorded and no errors raised."""
        with patch("src.policy_engine.get_policy_meter", return_value=None):
            engine = NativePolicyEngine(db_client)
            result = await engine.check_operation(
                agent_id="a1",
                agent_type="claude_code",
                operation="check_locks",
                context={"trust_level": 1},
            )

        # Should still work correctly
        assert result.allowed is True


# ---------------------------------------------------------------------------
# CedarPolicyEngine cache metric tests
# ---------------------------------------------------------------------------


class TestCedarCacheMetrics:
    """Verify cache hit/miss counter in CedarPolicyEngine._load_policies."""

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, mock_supabase, db_client):
        """First call should be a miss, second (within TTL) should be a hit."""
        mock_meter = _make_mock_meter()
        cache_counter = MagicMock()
        # create_histogram -> hist, create_counter calls: decision_counter, cache_counter
        mock_meter.create_counter.side_effect = [MagicMock(), cache_counter]

        with (
            patch("src.policy_engine.get_policy_meter", return_value=mock_meter),
            patch("src.policy_engine.CedarPolicyEngine.__init__", return_value=None),
        ):
            from src.policy_engine import CedarPolicyEngine

            engine = CedarPolicyEngine.__new__(CedarPolicyEngine)
            engine._db = db_client
            engine._policies_cache = None
            engine._policies_cache_time = 0.0
            engine._schema_cache = None
            engine._cedarpy = MagicMock()

            # Mock the DB via _db (property 'db' has no setter)
            mock_db = MagicMock()
            mock_db.query = AsyncMock(
                return_value=[{"policy_text": "permit(principal, action, resource);"}]
            )
            engine._db = mock_db

            mock_config = MagicMock()
            mock_config.policy_engine.policy_cache_ttl_seconds = 300
            mock_config.policy_engine.enable_code_fallback = True

            with patch("src.policy_engine.get_config", return_value=mock_config):
                # First call: cache miss
                await engine._load_policies()
                # Second call: cache hit (within TTL)
                await engine._load_policies()

        # Check calls to cache_counter
        calls = cache_counter.add.call_args_list
        assert len(calls) == 2
        # First call: miss
        assert calls[0][0] == (1, {"result": "miss"})
        # Second call: hit
        assert calls[1][0] == (1, {"result": "hit"})

    @pytest.mark.asyncio
    async def test_cache_counter_not_called_when_disabled(
        self, mock_supabase, db_client
    ):
        """When meter is None, cache counter is not called."""
        with (
            patch("src.policy_engine.get_policy_meter", return_value=None),
            patch("src.policy_engine.CedarPolicyEngine.__init__", return_value=None),
        ):
            from src.policy_engine import CedarPolicyEngine

            engine = CedarPolicyEngine.__new__(CedarPolicyEngine)
            engine._db = db_client
            engine._policies_cache = None
            engine._policies_cache_time = 0.0
            engine._schema_cache = None
            engine._cedarpy = MagicMock()

            mock_db = MagicMock()
            mock_db.query = AsyncMock(
                return_value=[{"policy_text": "permit(principal, action, resource);"}]
            )
            engine._db = mock_db

            mock_config = MagicMock()
            mock_config.policy_engine.policy_cache_ttl_seconds = 300
            mock_config.policy_engine.enable_code_fallback = True

            with patch("src.policy_engine.get_config", return_value=mock_config):
                # Should not raise even though instruments are all None
                await engine._load_policies()


# ---------------------------------------------------------------------------
# GuardrailsService metric tests
# ---------------------------------------------------------------------------


class TestGuardrailsServiceMetrics:
    """Verify GuardrailsService records OTel metrics."""

    @pytest.mark.asyncio
    async def test_safe_operation_records_duration(self, mock_supabase, db_client):
        """A safe operation should record duration with outcome='safe'."""
        mock_meter = _make_mock_meter()
        hist = MagicMock()
        violation_counter = MagicMock()
        mock_meter.create_histogram.return_value = hist
        mock_meter.create_counter.return_value = violation_counter

        with patch("src.guardrails.get_policy_meter", return_value=mock_meter):
            svc = GuardrailsService(db_client)
            # Preload patterns cache to avoid DB call
            svc._patterns_cache = []
            svc._cache_expiry = float("inf")

            result = await svc.check_operation(
                operation_text="echo hello",
                trust_level=2,
            )

        assert result.safe is True
        hist.record.assert_called_once()
        args, _ = hist.record.call_args
        assert args[1]["outcome"] == "safe"
        # No violations — counter should not be called
        violation_counter.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_violation_records_counter(self, mock_supabase, db_client):
        """Detected violations should increment the violation counter."""
        mock_meter = _make_mock_meter()
        hist = MagicMock()
        violation_counter = MagicMock()
        mock_meter.create_histogram.return_value = hist
        mock_meter.create_counter.return_value = violation_counter

        with (
            patch("src.guardrails.get_policy_meter", return_value=mock_meter),
            patch("src.guardrails.get_audit_service") as mock_audit,
        ):
            mock_audit.return_value.log_operation = AsyncMock()

            svc = GuardrailsService(db_client)
            # Use fallback patterns which include git_force_push
            from src.guardrails import FALLBACK_PATTERNS, GuardrailPattern

            svc._patterns_cache = [
                GuardrailPattern.from_dict(p) for p in FALLBACK_PATTERNS
            ]
            svc._cache_expiry = float("inf")

            result = await svc.check_operation(
                operation_text="git push origin main --force",
                trust_level=1,
                agent_id="test-agent",
                agent_type="test",
            )

        assert result.safe is False
        assert len(result.violations) >= 1

        # Duration recorded with outcome='violation'
        args, _ = hist.record.call_args
        assert args[1]["outcome"] == "violation"

        # Violation counter incremented for each violation
        assert violation_counter.add.call_count == len(result.violations)
        first_call_labels = violation_counter.add.call_args_list[0][0][1]
        assert "pattern" in first_call_labels
        assert "severity" in first_call_labels

    @pytest.mark.asyncio
    async def test_no_metrics_when_disabled(self, mock_supabase, db_client):
        """When meter is None, no metrics are recorded and no errors raised."""
        with patch("src.guardrails.get_policy_meter", return_value=None):
            svc = GuardrailsService(db_client)
            svc._patterns_cache = []
            svc._cache_expiry = float("inf")

            result = await svc.check_operation(
                operation_text="echo hello",
                trust_level=2,
            )

        assert result.safe is True
