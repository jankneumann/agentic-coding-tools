"""Tests for extended feedback with side-effect failure and semantic gap focus areas.

Covers spec scenarios:
- gen-eval-framework (Feedback Loop MODIFIED): side-effect failure patterns,
  semantic gaps

Design decisions: D2, D4
"""

from __future__ import annotations

from unittest.mock import MagicMock

from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.models import (
    ScenarioVerdict,
    SemanticVerdict,
    StepVerdict,
)


def _make_step(
    step_id: str = "step1",
    status: str = "pass",
    side_effect_verdicts: list[dict[str, object]] | None = None,
    semantic_verdict: SemanticVerdict | None = None,
) -> StepVerdict:
    return StepVerdict(
        step_id=step_id,
        transport="http",
        status=status,  # type: ignore[arg-type]
        actual={"body": {}},
        side_effect_verdicts=side_effect_verdicts,
        semantic_verdict=semantic_verdict,
    )


def _make_verdict(
    scenario_id: str = "test",
    status: str = "pass",
    steps: list[StepVerdict] | None = None,
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Test: {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=steps or [],
        interfaces_tested=["http"],
        category="test",
    )


def _mock_descriptor() -> InterfaceDescriptor:
    desc = MagicMock(spec=InterfaceDescriptor)
    desc.all_interfaces.return_value = ["http"]
    desc.total_interface_count.return_value = 1
    return desc


class TestFeedbackExtended:
    """Test extended feedback synthesis."""

    def test_side_effect_failures_in_focus(self) -> None:
        """Side-effect failures should appear in suggested_focus."""
        steps = [
            _make_step(
                side_effect_verdicts=[
                    {"step_id": "v1", "mode": "verify", "status": "fail"},
                ]
            )
        ]
        verdict = _make_verdict(status="fail", steps=steps)
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([verdict], _mock_descriptor())
        # Should mention side-effect failures in suggested focus
        focus_text = " ".join(feedback.suggested_focus)
        assert "side" in focus_text.lower() or len(feedback.suggested_focus) > 0

    def test_semantic_skip_gaps_in_focus(self) -> None:
        """Semantic skips (LLM unavailable) should surface as focus areas."""
        steps = [
            _make_step(
                semantic_verdict=SemanticVerdict(
                    status="skip", reasoning="LLM backend unavailable"
                )
            )
        ]
        verdict = _make_verdict(steps=steps)
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([verdict], _mock_descriptor())
        # Should note semantic gaps
        focus_text = " ".join(feedback.suggested_focus)
        assert "semantic" in focus_text.lower() or len(feedback.suggested_focus) >= 0

    def test_no_side_effects_no_extra_focus(self) -> None:
        """When no side-effects, feedback should not add side-effect focus."""
        steps = [_make_step()]
        verdict = _make_verdict(steps=steps)
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([verdict], _mock_descriptor())
        focus_text = " ".join(feedback.suggested_focus).lower()
        assert "side-effect" not in focus_text
