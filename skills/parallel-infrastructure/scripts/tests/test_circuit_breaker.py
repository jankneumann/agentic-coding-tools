"""Tests for circuit_breaker module."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from circuit_breaker import CircuitBreaker


def _make_packages() -> list[dict[str, Any]]:
    """Diamond DAG with timeout/retry settings."""
    return [
        {
            "package_id": "wp-contracts",
            "task_type": "contracts",
            "depends_on": [],
            "timeout_minutes": 30,
            "retry_budget": 1,
        },
        {
            "package_id": "wp-backend",
            "task_type": "implement",
            "depends_on": ["wp-contracts"],
            "timeout_minutes": 60,
            "retry_budget": 2,
        },
        {
            "package_id": "wp-frontend",
            "task_type": "implement",
            "depends_on": ["wp-contracts"],
            "timeout_minutes": 60,
            "retry_budget": 1,
        },
        {
            "package_id": "wp-integration",
            "task_type": "integrate",
            "depends_on": ["wp-backend", "wp-frontend"],
            "timeout_minutes": 120,
            "retry_budget": 0,
        },
    ]


@pytest.fixture
def breaker() -> CircuitBreaker:
    return CircuitBreaker(packages=_make_packages())


class TestTimeoutAndBudget:
    def test_get_timeout(self, breaker: CircuitBreaker) -> None:
        assert breaker.get_timeout_minutes("wp-contracts") == 30
        assert breaker.get_timeout_minutes("wp-backend") == 60
        assert breaker.get_timeout_minutes("wp-integration") == 120

    def test_get_timeout_default(self) -> None:
        cb = CircuitBreaker(
            packages=[{"package_id": "wp-x"}],
            default_timeout_minutes=45,
        )
        assert cb.get_timeout_minutes("wp-x") == 45

    def test_get_retry_budget(self, breaker: CircuitBreaker) -> None:
        assert breaker.get_retry_budget("wp-contracts") == 1
        assert breaker.get_retry_budget("wp-backend") == 2
        assert breaker.get_retry_budget("wp-integration") == 0

    def test_get_retry_budget_default(self) -> None:
        cb = CircuitBreaker(
            packages=[{"package_id": "wp-x"}],
            default_retry_budget=3,
        )
        assert cb.get_retry_budget("wp-x") == 3


class TestHeartbeat:
    def test_heartbeat_records_time(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-backend", now)
        # Not stuck if checked immediately
        stuck = breaker.check_stuck_packages(now + timedelta(minutes=1))
        assert stuck == []

    def test_start_monitoring(self, breaker: CircuitBreaker) -> None:
        breaker.start_monitoring("wp-backend")
        assert breaker._heartbeats.get("wp-backend") is not None


class TestStuckDetection:
    def test_not_stuck_within_timeout(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-backend", now)
        stuck = breaker.check_stuck_packages(now + timedelta(minutes=30))
        assert stuck == []

    def test_stuck_after_timeout(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-backend", now)
        stuck = breaker.check_stuck_packages(now + timedelta(minutes=61))
        assert len(stuck) == 1
        assert stuck[0]["package_id"] == "wp-backend"
        assert stuck[0]["timeout_minutes"] == 60
        assert stuck[0]["elapsed_minutes"] > 60

    def test_stuck_respects_per_package_timeout(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-contracts", now)  # 30 min timeout
        breaker.heartbeat("wp-backend", now)  # 60 min timeout

        check_time = now + timedelta(minutes=35)
        stuck = breaker.check_stuck_packages(check_time)
        assert len(stuck) == 1
        assert stuck[0]["package_id"] == "wp-contracts"

    def test_tripped_packages_not_reported_as_stuck(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-backend", now)
        breaker.trip("wp-backend")
        stuck = breaker.check_stuck_packages(now + timedelta(minutes=120))
        assert stuck == []

    def test_heartbeat_refresh_resets_timer(self, breaker: CircuitBreaker) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        breaker.heartbeat("wp-backend", now)
        # Refresh heartbeat at minute 50
        breaker.heartbeat("wp-backend", now + timedelta(minutes=50))
        # Check at minute 100 — only 50 minutes since last heartbeat
        stuck = breaker.check_stuck_packages(now + timedelta(minutes=100))
        assert stuck == []


class TestRetryBudget:
    def test_can_retry_with_budget(self, breaker: CircuitBreaker) -> None:
        assert breaker.can_retry("wp-backend") is True  # budget=2, attempts=0

    def test_cannot_retry_zero_budget(self, breaker: CircuitBreaker) -> None:
        assert breaker.can_retry("wp-integration") is False  # budget=0

    def test_cannot_retry_exhausted(self, breaker: CircuitBreaker) -> None:
        breaker.record_attempt("wp-contracts")  # budget=1, attempt=1
        assert breaker.can_retry("wp-contracts") is False

    def test_multiple_retries(self, breaker: CircuitBreaker) -> None:
        assert breaker.can_retry("wp-backend") is True  # budget=2, attempts=0
        breaker.record_attempt("wp-backend")  # attempts=1
        assert breaker.can_retry("wp-backend") is True  # 1 < 2
        breaker.record_attempt("wp-backend")  # attempts=2
        assert breaker.can_retry("wp-backend") is False  # 2 >= 2

    def test_attempt_count_tracking(self, breaker: CircuitBreaker) -> None:
        assert breaker.get_attempt_count("wp-backend") == 0
        breaker.record_attempt("wp-backend")
        assert breaker.get_attempt_count("wp-backend") == 1


class TestTripping:
    def test_trip(self, breaker: CircuitBreaker) -> None:
        breaker.trip("wp-backend")
        assert breaker.is_tripped("wp-backend") is True

    def test_not_tripped_by_default(self, breaker: CircuitBreaker) -> None:
        assert breaker.is_tripped("wp-backend") is False


class TestDependencyPropagation:
    def test_direct_dependents(self, breaker: CircuitBreaker) -> None:
        deps = breaker.get_dependent_packages("wp-contracts")
        assert set(deps) == {"wp-backend", "wp-frontend"}

    def test_no_dependents(self, breaker: CircuitBreaker) -> None:
        deps = breaker.get_dependent_packages("wp-integration")
        assert deps == []

    def test_transitive_dependents(self, breaker: CircuitBreaker) -> None:
        deps = breaker.get_transitive_dependents("wp-contracts")
        assert set(deps) == {"wp-backend", "wp-frontend", "wp-integration"}

    def test_transitive_from_midpoint(self, breaker: CircuitBreaker) -> None:
        deps = breaker.get_transitive_dependents("wp-backend")
        assert deps == ["wp-integration"]


class TestStatusSummary:
    def test_summary_structure(self, breaker: CircuitBreaker) -> None:
        breaker.start_monitoring("wp-backend")
        breaker.record_attempt("wp-backend")
        breaker.trip("wp-contracts")

        summary = breaker.get_status_summary()
        assert summary["monitored"] == 1
        assert summary["tripped"] == ["wp-contracts"]
        assert summary["attempt_counts"]["wp-backend"] == 1
        assert "wp-backend" in summary["packages"]
        assert summary["packages"]["wp-backend"]["attempts"] == 1
        assert summary["packages"]["wp-contracts"]["tripped"] is True
