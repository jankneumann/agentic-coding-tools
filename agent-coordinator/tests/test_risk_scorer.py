"""Tests for the contextual risk scoring service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.risk_scorer import (
    ADMIN_OPERATIONS,
    READ_OPERATIONS,
    SENSITIVE_RESOURCES,
    WRITE_OPERATIONS,
    RiskScorer,
    get_risk_scorer,
    reset_risk_scorer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(violation_rows: list[dict[str, Any]] | None = None) -> AsyncMock:
    """Return a mock DatabaseClient whose .query returns *violation_rows*."""
    db = AsyncMock()
    db.query.return_value = violation_rows if violation_rows is not None else []
    return db


# ---------------------------------------------------------------------------
# compute_score integration-style tests
# ---------------------------------------------------------------------------

class TestComputeScore:
    """End-to-end risk score computation."""

    async def test_compute_score_low_risk(self) -> None:
        """Trust 3, read op, no violations → score ≤ 0.3 → allow."""
        db = _make_mock_db([])
        scorer = RiskScorer(db=db)
        result = await scorer.compute_score(
            agent_id="agent-1",
            trust_level=3,
            operation="recall",
            session_age_seconds=600,
        )
        assert result.score <= 0.3
        assert result.recommendation == "allow"
        assert isinstance(result.factors, dict)

    async def test_compute_score_medium_risk(self) -> None:
        """Trust 2, write op, 1 violation → score in (0.3, 0.7] → log."""
        db = _make_mock_db([{"id": "v1"}])
        scorer = RiskScorer(db=db)
        result = await scorer.compute_score(
            agent_id="agent-1",
            trust_level=2,
            operation="acquire_lock",
            session_age_seconds=120,
        )
        assert 0.3 < result.score <= 0.7
        assert result.recommendation == "log"

    async def test_compute_score_high_risk(self) -> None:
        """Trust 1, admin op, 3 violations → score > 0.7 → approval_required."""
        db = _make_mock_db([{"id": f"v{i}"} for i in range(3)])
        scorer = RiskScorer(db=db)
        result = await scorer.compute_score(
            agent_id="agent-1",
            trust_level=1,
            operation="force_push",
            resource=".env.production",
            session_age_seconds=30,
        )
        assert result.score > 0.7
        assert result.recommendation == "approval_required"

    async def test_score_clamped_between_0_and_1(self) -> None:
        """Score must always be in [0.0, 1.0] regardless of extreme inputs."""
        db = _make_mock_db([{"id": f"v{i}"} for i in range(50)])
        scorer = RiskScorer(db=db)
        result = await scorer.compute_score(
            agent_id="agent-1",
            trust_level=0,
            operation="force_push",
            resource="secrets.json",
            session_age_seconds=0,
        )
        assert 0.0 <= result.score <= 1.0

        # Very low risk scenario
        db2 = _make_mock_db([])
        scorer2 = RiskScorer(db=db2)
        result2 = await scorer2.compute_score(
            agent_id="agent-1",
            trust_level=3,
            operation="recall",
            session_age_seconds=99999,
        )
        assert 0.0 <= result2.score <= 1.0

    async def test_custom_thresholds_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RISK_LOW_THRESHOLD / RISK_HIGH_THRESHOLD env vars change recommendation."""
        monkeypatch.setenv("RISK_LOW_THRESHOLD", "0.1")
        monkeypatch.setenv("RISK_HIGH_THRESHOLD", "0.2")

        db = _make_mock_db([])
        scorer = RiskScorer(db=db)
        result = await scorer.compute_score(
            agent_id="agent-1",
            trust_level=2,
            operation="acquire_lock",
            session_age_seconds=600,
        )
        # With lowered thresholds, a moderate score becomes approval_required
        assert result.recommendation in {"log", "approval_required"}


# ---------------------------------------------------------------------------
# Individual factor tests
# ---------------------------------------------------------------------------

class TestTrustFactor:
    """RiskScorer._trust_factor static method."""

    def test_trust_level_0(self) -> None:
        assert RiskScorer._trust_factor(0) == 1.0

    def test_trust_level_1(self) -> None:
        assert RiskScorer._trust_factor(1) == pytest.approx(0.7)

    def test_trust_level_2(self) -> None:
        assert RiskScorer._trust_factor(2) == pytest.approx(0.4)

    def test_trust_level_3(self) -> None:
        assert RiskScorer._trust_factor(3) == pytest.approx(0.1)

    def test_trust_level_clamped_high(self) -> None:
        """Trust level > 3 should not go below 0.0."""
        assert RiskScorer._trust_factor(10) == 0.0


class TestOperationFactor:
    """RiskScorer._operation_factor static method."""

    def test_admin_operation(self) -> None:
        for op in ADMIN_OPERATIONS:
            assert RiskScorer._operation_factor(op) == 0.9

    def test_write_operation(self) -> None:
        for op in WRITE_OPERATIONS:
            assert RiskScorer._operation_factor(op) == 0.5

    def test_read_operation(self) -> None:
        for op in READ_OPERATIONS:
            assert RiskScorer._operation_factor(op) == 0.1

    def test_unknown_operation(self) -> None:
        assert RiskScorer._operation_factor("some_unknown_op") == 0.5


class TestResourceFactor:
    """RiskScorer._resource_factor static method."""

    def test_none_resource(self) -> None:
        assert RiskScorer._resource_factor(None) == 0.3

    def test_normal_resource(self) -> None:
        assert RiskScorer._resource_factor("src/main.py") == 0.3

    def test_sensitive_patterns(self) -> None:
        for pattern in SENSITIVE_RESOURCES:
            assert RiskScorer._resource_factor(f"/path/{pattern}/file") == 0.9

    def test_case_insensitive(self) -> None:
        assert RiskScorer._resource_factor("SECRETS.JSON") == 0.9
        assert RiskScorer._resource_factor(".ENV.production") == 0.9


class TestViolationFactor:
    """RiskScorer._violation_factor static method."""

    def test_zero_violations(self) -> None:
        assert RiskScorer._violation_factor(0) == 0.0

    def test_one_violation(self) -> None:
        assert RiskScorer._violation_factor(1) == pytest.approx(0.3)

    def test_two_violations(self) -> None:
        assert RiskScorer._violation_factor(2) == pytest.approx(0.45)

    def test_five_violations(self) -> None:
        result = RiskScorer._violation_factor(5)
        assert result == pytest.approx(0.9)

    def test_many_violations_clamped(self) -> None:
        assert RiskScorer._violation_factor(100) <= 0.9


class TestSessionAgeFactor:
    """RiskScorer._session_age_factor static method."""

    def test_zero_seconds(self) -> None:
        assert RiskScorer._session_age_factor(0) == 0.5

    def test_30_seconds(self) -> None:
        assert RiskScorer._session_age_factor(30) == 0.5

    def test_120_seconds(self) -> None:
        assert RiskScorer._session_age_factor(120) == 0.3

    def test_600_seconds(self) -> None:
        assert RiskScorer._session_age_factor(600) == 0.1


# ---------------------------------------------------------------------------
# Violation count DB query
# ---------------------------------------------------------------------------

class TestGetViolationCount:
    """RiskScorer.get_violation_count with mocked DB."""

    async def test_returns_row_count(self) -> None:
        db = _make_mock_db([{"id": "v1"}, {"id": "v2"}])
        scorer = RiskScorer(db=db)
        count = await scorer.get_violation_count("agent-1", window_seconds=3600)
        assert count == 2
        db.query.assert_called_once()
        # Verify correct table and PostgREST filter shape
        call_args = db.query.call_args
        assert call_args[0][0] == "guardrail_violations"
        assert "agent_id=eq.agent-1" in call_args[1]["query_params"]
        assert "blocked=eq.true" in call_args[1]["query_params"]

    async def test_returns_zero_on_db_error(self) -> None:
        db = AsyncMock()
        db.query.side_effect = RuntimeError("connection lost")
        scorer = RiskScorer(db=db)
        count = await scorer.get_violation_count("agent-1")
        assert count == 0


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

class TestSingleton:
    """get_risk_scorer / reset_risk_scorer module-level helpers."""

    def test_get_risk_scorer_returns_same_instance(self) -> None:
        reset_risk_scorer()
        a = get_risk_scorer()
        b = get_risk_scorer()
        assert a is b

    def test_reset_clears_singleton(self) -> None:
        reset_risk_scorer()
        a = get_risk_scorer()
        reset_risk_scorer()
        b = get_risk_scorer()
        assert a is not b
