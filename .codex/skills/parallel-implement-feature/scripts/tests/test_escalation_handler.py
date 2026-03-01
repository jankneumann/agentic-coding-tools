"""Tests for escalation_handler module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from escalation_handler import EscalationAction, EscalationDecision, EscalationHandler


def _make_escalation(
    esc_type: str,
    summary: str = "Test escalation",
    package_id: str = "wp-backend",
    impacted_packages: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal escalation dict."""
    esc: dict[str, Any] = {
        "escalation_id": f"esc-{esc_type.lower()}-001",
        "feature_id": "test-feature",
        "package_id": package_id,
        "type": esc_type,
        "severity": "HIGH",
        "summary": summary,
        "detected_at": "2026-01-01T00:00:00Z",
    }
    if impacted_packages:
        esc["impact"] = {"impacted_packages": impacted_packages}
    return esc


@pytest.fixture
def handler() -> EscalationHandler:
    return EscalationHandler(
        feature_id="test-feature",
        contracts_revision=1,
        plan_revision=1,
    )


class TestContractRevisionRequired:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("CONTRACT_REVISION_REQUIRED", impacted_packages=["wp-backend", "wp-frontend"])
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.PAUSE_AND_RESCHEDULE
        assert decision.pause_required is True
        assert decision.revision_bump == "contracts"

    def test_impacted_packages(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("CONTRACT_REVISION_REQUIRED", impacted_packages=["wp-backend"])
        decision = handler.handle(esc)
        assert decision.impacted_packages == ["wp-backend"]

    def test_no_impacted_packages(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("CONTRACT_REVISION_REQUIRED")
        decision = handler.handle(esc)
        assert decision.impacted_packages is None


class TestPlanRevisionRequired:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("PLAN_REVISION_REQUIRED")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.PAUSE_AND_REPLAN
        assert decision.pause_required is True
        assert decision.revision_bump == "plan"


class TestResourceConflict:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("RESOURCE_CONFLICT")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.RETRY_PACKAGE
        assert decision.pause_required is False


class TestVerificationInfeasible:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("VERIFICATION_INFEASIBLE")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.FAIL_PACKAGE
        assert decision.requires_human is True
        assert decision.pause_required is False


class TestScopeViolation:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("SCOPE_VIOLATION")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.FAIL_PACKAGE
        assert decision.requires_human is False


class TestEnvResourceConflict:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("ENV_RESOURCE_CONFLICT")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.RETRY_PACKAGE


class TestSecurityEscalation:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("SECURITY_ESCALATION")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.REQUIRE_HUMAN
        assert decision.pause_required is True
        assert decision.requires_human is True


class TestFlakyTestQuarantine:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("FLAKY_TEST_QUARANTINE_REQUEST")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.QUARANTINE_AND_RETRY


class TestUnknownType:
    def test_action(self, handler: EscalationHandler) -> None:
        esc = _make_escalation("UNKNOWN_TYPE")
        decision = handler.handle(esc)
        assert decision.action == EscalationAction.REQUIRE_HUMAN
        assert decision.requires_human is True


class TestDecisionTracking:
    def test_decisions_recorded(self, handler: EscalationHandler) -> None:
        handler.handle(_make_escalation("SCOPE_VIOLATION"))
        handler.handle(_make_escalation("RESOURCE_CONFLICT"))
        decisions = handler.get_decisions()
        assert len(decisions) == 2
        assert decisions[0]["type"] == "SCOPE_VIOLATION"
        assert decisions[1]["type"] == "RESOURCE_CONFLICT"

    def test_decision_to_dict(self) -> None:
        decision = EscalationDecision(
            action=EscalationAction.PAUSE_AND_RESCHEDULE,
            reason="test",
            pause_required=True,
            revision_bump="contracts",
            impacted_packages=["wp-a"],
        )
        d = decision.to_dict()
        assert d["action"] == "pause_and_reschedule"
        assert d["pause_required"] is True
        assert d["revision_bump"] == "contracts"
        assert d["impacted_packages"] == ["wp-a"]

    def test_decision_to_dict_minimal(self) -> None:
        decision = EscalationDecision(
            action=EscalationAction.RETRY_PACKAGE,
            reason="test",
        )
        d = decision.to_dict()
        assert "revision_bump" not in d
        assert "impacted_packages" not in d


class TestAllEscalationTypes:
    """Ensure every schema-defined escalation type has a handler."""

    SCHEMA_TYPES = [
        "CONTRACT_REVISION_REQUIRED",
        "PLAN_REVISION_REQUIRED",
        "RESOURCE_CONFLICT",
        "VERIFICATION_INFEASIBLE",
        "SCOPE_VIOLATION",
        "ENV_RESOURCE_CONFLICT",
        "SECURITY_ESCALATION",
        "FLAKY_TEST_QUARANTINE_REQUEST",
    ]

    @pytest.mark.parametrize("esc_type", SCHEMA_TYPES)
    def test_handler_exists(self, handler: EscalationHandler, esc_type: str) -> None:
        esc = _make_escalation(esc_type)
        decision = handler.handle(esc)
        # Should not fall through to unknown handler
        assert "Unknown escalation type" not in decision.reason
