"""Fail-closed blocker policy independent of consensus matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_ACTIONABLE = frozenset({"fix", "regenerate", "escalate"})
_MEDIUM_OR_HIGHER = frozenset({"medium", "high", "critical"})


@dataclass(frozen=True)
class BlockingDecision:
    integration_blocking: bool
    convergence_blocking: bool

    @property
    def effective_blocking(self) -> bool:
        return self.integration_blocking or self.convergence_blocking


def _is_valid_non_blocking_adjudication(adjudication: dict[str, Any]) -> bool:
    status = adjudication.get("status")
    if status in {"fixed", "false_positive"}:
        return bool(adjudication.get("rationale")) and bool(adjudication.get("evidence"))
    if status != "accepted_risk":
        return False
    authorization = adjudication.get("authorization")
    return (
        bool(adjudication.get("rationale"))
        and isinstance(authorization, dict)
        and authorization.get("actor_type") == "human"
        and bool(authorization.get("actor_id"))
        and bool(authorization.get("approval_ref"))
    )


def evaluate_blocking(
    *,
    policy_status: str,
    criticality: str,
    vendor_dispositions: dict[str, str],
    adjudication: dict[str, Any],
) -> BlockingDecision:
    """Derive independent integration and convergence blockers.

    Matching only provides ``policy_status``.  It cannot waive an actionable
    finding: valid evidence-backed adjudication is the only waiver mechanism.
    """
    if _is_valid_non_blocking_adjudication(adjudication):
        return BlockingDecision(False, False)

    actionable = bool(_ACTIONABLE.intersection(vendor_dispositions.values()))
    disagreement = policy_status == "disagreement"
    integration = disagreement or (policy_status == "confirmed" and actionable)
    convergence = disagreement or (
        criticality in _MEDIUM_OR_HIGHER and actionable
    )
    return BlockingDecision(integration, convergence)
