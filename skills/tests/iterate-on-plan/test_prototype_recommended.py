"""Tests for the workflow.prototype-recommended advisory emitter.

Spec scenarios:
- skill-workflow.PrototypeRecommendationSignal.threshold-met
- skill-workflow.PrototypeRecommendationSignal.threshold-not-met
- skill-workflow.PrototypeRecommendationSignal.advisory-only

Design decisions: D8 (opt-in gating via iterate-on-plan suggestion).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "iterate-on-plan" / "scripts"
)
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from prototype_recommended import (
    PROTOTYPE_RECOMMENDED_THRESHOLD,
    PROTOTYPE_RECOMMENDED_TYPE,
    maybe_emit_prototype_recommended,
)


def _finding(
    type_: str = "clarity.missing-acceptance-criterion",
    criticality: str = "high",
) -> dict:
    return {
        "type": type_,
        "criticality": criticality,
        "description": f"sample finding {type_}",
    }


class TestThresholdMet:
    def test_three_high_clarity_findings_emit_recommendation(self) -> None:
        findings = [_finding(type_="clarity.x", criticality="high") for _ in range(3)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is not None
        assert result["type"] == PROTOTYPE_RECOMMENDED_TYPE
        # The advisory must reference the triggering findings so a human
        # can see WHY prototyping is being suggested.
        assert "3 high-criticality" in result["description"]

    def test_mixed_clarity_and_feasibility_count_together(self) -> None:
        # Spec wording: "≥3 high-criticality findings in clarity OR
        # feasibility combined". Two clarity + one feasibility = 3.
        findings = [
            _finding(type_="clarity.a", criticality="high"),
            _finding(type_="clarity.b", criticality="high"),
            _finding(type_="feasibility.c", criticality="high"),
        ]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is not None

    def test_six_findings_still_emit_only_one_advisory(self) -> None:
        # The advisory is a single finding, not one per trigger.
        findings = [_finding(type_="clarity.x", criticality="high") for _ in range(6)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is not None
        assert isinstance(result, dict)


class TestThresholdNotMet:
    def test_two_high_clarity_findings_no_emit(self) -> None:
        findings = [_finding(type_="clarity.x", criticality="high") for _ in range(2)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is None

    def test_three_medium_findings_no_emit(self) -> None:
        # Threshold is gated on HIGH criticality; medium doesn't count.
        findings = [_finding(type_="clarity.x", criticality="medium") for _ in range(3)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is None

    def test_three_high_security_findings_no_emit(self) -> None:
        # Other dimensions don't trigger — only clarity + feasibility.
        # Prototyping addresses uncertainty in shape, not risk in shape.
        findings = [_finding(type_="security.x", criticality="high") for _ in range(3)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result is None

    def test_empty_findings_no_emit(self) -> None:
        result = maybe_emit_prototype_recommended([], change_id="add-foo")
        assert result is None


class TestAdvisoryShape:
    """Spec: advisory-only — the finding never auto-triggers anything."""

    def test_finding_type_constant(self) -> None:
        assert PROTOTYPE_RECOMMENDED_TYPE == "workflow.prototype-recommended"

    def test_threshold_constant(self) -> None:
        # D8 default; a different value would be observable to integrators.
        assert PROTOTYPE_RECOMMENDED_THRESHOLD == 3

    def test_description_suggests_command(self) -> None:
        # Must point the human at /prototype-feature so they know how to act
        # on the suggestion (or ignore it).
        findings = [_finding(type_="clarity.x", criticality="high") for _ in range(3)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert "prototype-feature" in result["description"]
        assert "add-foo" in result["description"]

    def test_advisory_criticality_is_low(self) -> None:
        # Advisory findings should never block iteration. Use low so they
        # surface in reports without being mistaken for actionable issues.
        findings = [_finding(type_="clarity.x", criticality="high") for _ in range(3)]
        result = maybe_emit_prototype_recommended(findings, change_id="add-foo")
        assert result["criticality"] == "low"
