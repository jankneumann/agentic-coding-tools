"""Contextual risk scoring for graduated authorization decisions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .db import DatabaseClient, get_db

# Operation severity classification
ADMIN_OPERATIONS = frozenset({
    "force_push", "delete_branch", "cleanup_agents", "rollback_policy",
})
WRITE_OPERATIONS = frozenset({
    "acquire_lock", "release_lock", "complete_work", "submit_work",
    "remember", "write_handoff", "check_guardrails", "request_approval",
    "request_permission",
})
READ_OPERATIONS = frozenset({
    "check_locks", "get_work", "recall", "discover_agents",
    "read_handoff", "query_audit", "check_approval", "list_policy_versions",
})

# Resource sensitivity patterns
SENSITIVE_RESOURCES = frozenset({
    ".env", "credentials", "secrets", "private_key", "api_key",
    "cedar_policies", "agent_profiles", "audit_log",
})


@dataclass
class RiskScore:
    """Result of a risk scoring computation."""

    score: float
    factors: dict[str, float]
    recommendation: str  # "allow", "log", "approval_required", "block"


class RiskScorer:
    """Compute contextual risk scores for authorization decisions."""

    def __init__(self, db: DatabaseClient | None = None) -> None:
        self._db = db
        # Weights for risk factors (must sum to 1.0)
        self._weights = {
            "trust": 0.30,
            "operation": 0.25,
            "resource": 0.20,
            "violations": 0.15,
            "session_age": 0.10,
        }

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def compute_score(
        self,
        agent_id: str,
        trust_level: int,
        operation: str,
        *,
        resource: str | None = None,
        session_age_seconds: int = 0,
        violation_window_seconds: int = 3600,
    ) -> RiskScore:
        """Compute a risk score (0.0-1.0) for an operation."""
        trust_factor = self._trust_factor(trust_level)
        op_factor = self._operation_factor(operation)
        resource_factor = self._resource_factor(resource)
        violation_count = await self.get_violation_count(
            agent_id, violation_window_seconds,
        )
        violation_factor = self._violation_factor(violation_count)
        session_factor = self._session_age_factor(session_age_seconds)

        factors = {
            "trust": trust_factor,
            "operation": op_factor,
            "resource": resource_factor,
            "violations": violation_factor,
            "session_age": session_factor,
        }

        score = sum(factors[k] * self._weights[k] for k in factors)
        score = max(0.0, min(1.0, score))

        low = float(os.environ.get("RISK_LOW_THRESHOLD", "0.3"))
        high = float(os.environ.get("RISK_HIGH_THRESHOLD", "0.7"))

        if score <= low:
            recommendation = "allow"
        elif score <= high:
            recommendation = "log"
        else:
            recommendation = "approval_required"

        return RiskScore(
            score=round(score, 4),
            factors=factors,
            recommendation=recommendation,
        )

    async def get_violation_count(
        self, agent_id: str, window_seconds: int = 3600,
    ) -> int:
        """Count recent guardrail violations for an agent."""
        cutoff = (
            datetime.now(UTC) - timedelta(seconds=window_seconds)
        ).isoformat()
        try:
            rows = await self.db.query(
                "guardrail_violations",
                query_params=f"agent_id=eq.{agent_id}&created_at=gt.{cutoff}&blocked=eq.true",
            )
            return len(rows)
        except Exception:
            return 0

    @staticmethod
    def _trust_factor(trust_level: int) -> float:
        """Lower trust = higher risk. Trust 0=1.0, 1=0.7, 2=0.4, 3=0.1."""
        return max(0.0, min(1.0, 1.0 - (trust_level * 0.3)))

    @staticmethod
    def _operation_factor(operation: str) -> float:
        """Admin ops = high risk, write = medium, read = low."""
        if operation in ADMIN_OPERATIONS:
            return 0.9
        if operation in WRITE_OPERATIONS:
            return 0.5
        if operation in READ_OPERATIONS:
            return 0.1
        return 0.5  # unknown operations default to medium

    @staticmethod
    def _resource_factor(resource: str | None) -> float:
        """Sensitive resources = higher risk."""
        if not resource:
            return 0.3
        resource_lower = resource.lower()
        for pattern in SENSITIVE_RESOURCES:
            if pattern in resource_lower:
                return 0.9
        return 0.3

    @staticmethod
    def _violation_factor(count: int) -> float:
        """More recent violations = higher risk. 0=0.0, 1=0.3, 3+=0.9."""
        if count == 0:
            return 0.0
        if count <= 2:
            return 0.3 + (count - 1) * 0.15
        return min(0.9, 0.3 + count * 0.15)

    @staticmethod
    def _session_age_factor(age_seconds: int) -> float:
        """Very new sessions have slightly higher risk. >5min = low."""
        if age_seconds < 60:
            return 0.5
        if age_seconds < 300:
            return 0.3
        return 0.1


# Module-level singleton
_risk_scorer: RiskScorer | None = None


def get_risk_scorer() -> RiskScorer:
    """Get the global risk scorer instance."""
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = RiskScorer()
    return _risk_scorer


def reset_risk_scorer() -> None:
    """Reset the global risk scorer (for testing)."""
    global _risk_scorer
    _risk_scorer = None
