"""Escalation handling for parallel-implement-feature.

Implements deterministic decision procedures per escalation type.
Each escalation type has a prescribed action; the orchestrator does
NOT make conversational decisions about escalation handling.

Escalation Types (from work-queue-result.schema.json):
- CONTRACT_REVISION_REQUIRED — Pause, bump contracts.revision, reschedule
- PLAN_REVISION_REQUIRED — Pause, bump plan_revision, replan
- RESOURCE_CONFLICT — Retry with backoff or fail
- VERIFICATION_INFEASIBLE — Downgrade tier or fail (no silent downgrade)
- SCOPE_VIOLATION — Fail package, report violation
- ENV_RESOURCE_CONFLICT — Allocate new resources or fail
- SECURITY_ESCALATION — Fail, require human review
- FLAKY_TEST_QUARANTINE_REQUEST — Quarantine test, retry

Usage:
    from escalation_handler import EscalationHandler

    handler = EscalationHandler(feature_id="add-auth", contracts_revision=1, plan_revision=1)
    decision = handler.handle(escalation)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EscalationAction(str, Enum):
    """Actions the orchestrator can take in response to an escalation."""

    PAUSE_AND_RESCHEDULE = "pause_and_reschedule"
    PAUSE_AND_REPLAN = "pause_and_replan"
    RETRY_PACKAGE = "retry_package"
    FAIL_PACKAGE = "fail_package"
    QUARANTINE_AND_RETRY = "quarantine_and_retry"
    REQUIRE_HUMAN = "require_human"


@dataclass
class EscalationDecision:
    """The orchestrator's decision for an escalation."""

    action: EscalationAction
    reason: str
    pause_required: bool = False
    revision_bump: str | None = None  # "contracts" or "plan" or None
    impacted_packages: list[str] | None = None
    requires_human: bool = False

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": self.action.value,
            "reason": self.reason,
            "pause_required": self.pause_required,
            "requires_human": self.requires_human,
        }
        if self.revision_bump:
            result["revision_bump"] = self.revision_bump
        if self.impacted_packages:
            result["impacted_packages"] = self.impacted_packages
        return result


class EscalationHandler:
    """Deterministic escalation handler for the orchestrator.

    Maps each escalation type to a prescribed action. No conversational
    decision-making — each type has exactly one handling procedure.
    """

    def __init__(
        self,
        feature_id: str,
        contracts_revision: int,
        plan_revision: int,
    ):
        self.feature_id = feature_id
        self.contracts_revision = contracts_revision
        self.plan_revision = plan_revision
        self._decisions: list[dict[str, Any]] = []

    def handle(self, escalation: dict[str, Any]) -> EscalationDecision:
        """Handle an escalation and return the prescribed decision.

        Args:
            escalation: Escalation dict conforming to the Escalation $def
                        in work-queue-result.schema.json.

        Returns:
            EscalationDecision with the prescribed action.
        """
        esc_type = escalation.get("type", "")
        handler_func = self._handlers.get(esc_type)
        if handler_func is not None:
            decision = handler_func(self, escalation)
        else:
            decision = self._handle_unknown(escalation)
        self._decisions.append({
            "escalation_id": escalation.get("escalation_id"),
            "type": esc_type,
            "decision": decision.to_dict(),
        })
        return decision

    def get_decisions(self) -> list[dict[str, Any]]:
        """Return all decisions made so far."""
        return list(self._decisions)

    def _handle_contract_revision_required(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """CONTRACT_REVISION_REQUIRED: Pause all, bump contracts.revision, reschedule."""
        impacted = escalation.get("impact", {}).get("impacted_packages", [])
        return EscalationDecision(
            action=EscalationAction.PAUSE_AND_RESCHEDULE,
            reason=f"Contract revision required: {escalation.get('summary', '')}",
            pause_required=True,
            revision_bump="contracts",
            impacted_packages=impacted or None,
        )

    def _handle_plan_revision_required(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """PLAN_REVISION_REQUIRED: Pause all, bump plan_revision, replan."""
        impacted = escalation.get("impact", {}).get("impacted_packages", [])
        return EscalationDecision(
            action=EscalationAction.PAUSE_AND_REPLAN,
            reason=f"Plan revision required: {escalation.get('summary', '')}",
            pause_required=True,
            revision_bump="plan",
            impacted_packages=impacted or None,
        )

    def _handle_resource_conflict(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """RESOURCE_CONFLICT: Retry with backoff."""
        return EscalationDecision(
            action=EscalationAction.RETRY_PACKAGE,
            reason=f"Resource conflict: {escalation.get('summary', '')}",
        )

    def _handle_verification_infeasible(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """VERIFICATION_INFEASIBLE: Fail package (no silent tier downgrade)."""
        return EscalationDecision(
            action=EscalationAction.FAIL_PACKAGE,
            reason=f"Verification infeasible (no silent downgrade): {escalation.get('summary', '')}",
            requires_human=True,
        )

    def _handle_scope_violation(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """SCOPE_VIOLATION: Fail the package."""
        return EscalationDecision(
            action=EscalationAction.FAIL_PACKAGE,
            reason=f"Scope violation: {escalation.get('summary', '')}",
        )

    def _handle_env_resource_conflict(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """ENV_RESOURCE_CONFLICT: Retry with resource reallocation."""
        return EscalationDecision(
            action=EscalationAction.RETRY_PACKAGE,
            reason=f"Environment resource conflict: {escalation.get('summary', '')}",
        )

    def _handle_security_escalation(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """SECURITY_ESCALATION: Fail, require human review."""
        return EscalationDecision(
            action=EscalationAction.REQUIRE_HUMAN,
            reason=f"Security issue requires human review: {escalation.get('summary', '')}",
            pause_required=True,
            requires_human=True,
        )

    def _handle_flaky_test_quarantine(
        self, escalation: dict[str, Any]
    ) -> EscalationDecision:
        """FLAKY_TEST_QUARANTINE_REQUEST: Quarantine and retry."""
        return EscalationDecision(
            action=EscalationAction.QUARANTINE_AND_RETRY,
            reason=f"Flaky test quarantine: {escalation.get('summary', '')}",
        )

    def _handle_unknown(self, escalation: dict[str, Any]) -> EscalationDecision:
        """Unknown escalation type: require human."""
        return EscalationDecision(
            action=EscalationAction.REQUIRE_HUMAN,
            reason=f"Unknown escalation type '{escalation.get('type', '')}': {escalation.get('summary', '')}",
            requires_human=True,
        )

    _handlers: dict[str, Any] = {
        "CONTRACT_REVISION_REQUIRED": _handle_contract_revision_required,
        "PLAN_REVISION_REQUIRED": _handle_plan_revision_required,
        "RESOURCE_CONFLICT": _handle_resource_conflict,
        "VERIFICATION_INFEASIBLE": _handle_verification_infeasible,
        "SCOPE_VIOLATION": _handle_scope_violation,
        "ENV_RESOURCE_CONFLICT": _handle_env_resource_conflict,
        "SECURITY_ESCALATION": _handle_security_escalation,
        "FLAKY_TEST_QUARANTINE_REQUEST": _handle_flaky_test_quarantine,
    }
