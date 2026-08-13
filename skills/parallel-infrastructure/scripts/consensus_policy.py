"""Fail-closed blocker policy independent of consensus matching."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
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


TrustedApprovalResolver = Callable[[dict[str, Any]], bool]


def is_valid_non_blocking_adjudication(
    adjudication: dict[str, Any],
    *,
    trusted_approval_resolver: TrustedApprovalResolver | None = None,
) -> bool:
    """Return whether an adjudication may waive a blocker.

    ``accepted_risk`` is deliberately not self-authenticating: artifact data
    only supplies a reference.  A caller-owned trusted resolver must verify
    that reference against an approval system before the waiver takes effect.
    """
    status = adjudication.get("status")
    if status in {"fixed", "false_positive"}:
        evidence = adjudication.get("evidence")
        return (
            bool(adjudication.get("rationale"))
            and isinstance(evidence, list)
            and bool(evidence)
            and all(isinstance(item, str) and item for item in evidence)
        )
    if status != "accepted_risk":
        return False
    authorization = adjudication.get("authorization")
    if not (
        bool(adjudication.get("rationale"))
        and isinstance(authorization, dict)
        and authorization.get("actor_type") == "human"
        and isinstance(authorization.get("actor_id"), str)
        and bool(authorization["actor_id"])
        and authorization.get("mechanism") in {
            "coordinator_audit", "github_approval", "signed_local_record",
        }
        and isinstance(authorization.get("authorized_at"), str)
        and bool(authorization["authorized_at"])
        and isinstance(authorization.get("approval_ref"), str)
        and bool(authorization["approval_ref"])
        and trusted_approval_resolver is not None
    ):
        return False
    try:
        return bool(trusted_approval_resolver(authorization))
    except Exception:
        return False


def evaluate_blocking(
    *,
    policy_status: str,
    criticality: str,
    vendor_dispositions: dict[str, str],
    adjudication: dict[str, Any],
    trusted_approval_resolver: TrustedApprovalResolver | None = None,
) -> BlockingDecision:
    """Derive independent integration and convergence blockers.

    Matching only provides ``policy_status``.  It cannot waive an actionable
    finding: valid evidence-backed adjudication is the only waiver mechanism.
    """
    if is_valid_non_blocking_adjudication(
        adjudication,
        trusted_approval_resolver=trusted_approval_resolver,
    ):
        return BlockingDecision(False, False)

    actionable = bool(_ACTIONABLE.intersection(vendor_dispositions.values()))
    disagreement = policy_status == "disagreement"
    integration = disagreement or (policy_status == "confirmed" and actionable)
    convergence = disagreement or (
        criticality in _MEDIUM_OR_HIGHER and actionable
    )
    return BlockingDecision(integration, convergence)
