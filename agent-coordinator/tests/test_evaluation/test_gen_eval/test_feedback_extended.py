"""Tests for extended feedback synthesis (Phase 6).

Covers: side-effect failure focus areas and semantic evaluation gaps.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.models import (
    ScenarioVerdict,
    SemanticVerdict,
    SideEffectVerdict,
    StepVerdict,
)


def _mock_descriptor() -> InterfaceDescriptor:
    desc = MagicMock(spec=InterfaceDescriptor)
    desc.total_interface_count.return_value = 10
    desc.all_interfaces.return_value = [f"iface-{i}" for i in range(10)]
    return desc


class TestSideEffectFeedback:
    """Side-effect failures appear in suggested focus."""

    def test_side_effect_failure_in_focus(self) -> None:
        verdicts = [
            ScenarioVerdict(
                scenario_id="mem-lifecycle",
                scenario_name="Memory Lifecycle",
                status="fail",
                steps=[
                    StepVerdict(
                        step_id="store",
                        transport="http",
                        status="pass",
                        side_effect_verdicts=[
                            SideEffectVerdict(
                                step_id="check_audit",
                                mode="verify",
                                status="fail",
                                diff={"rows": {"expected": 1, "actual": 0}},
                            ),
                        ],
                    ),
                ],
                category="memory-crud",
                interfaces_tested=["POST /memory/store"],
            ),
        ]

        synthesizer = FeedbackSynthesizer()
        feedback = synthesizer.synthesize(verdicts, _mock_descriptor())

        # Side-effect failure should appear in suggested focus
        assert any("side-effect-failure:mem-lifecycle" in f for f in feedback.suggested_focus)


class TestSemanticFeedback:
    """Semantic gaps appear in suggested focus."""

    def test_semantic_skip_in_focus(self) -> None:
        verdicts = [
            ScenarioVerdict(
                scenario_id="search-relevance",
                scenario_name="Search Relevance",
                status="pass",
                steps=[
                    StepVerdict(
                        step_id="search",
                        transport="http",
                        status="pass",
                        semantic_verdict=SemanticVerdict(
                            status="skip",
                            reasoning="LLM unavailable",
                        ),
                    ),
                ],
                category="memory-crud",
                interfaces_tested=["POST /memory/query"],
            ),
        ]

        synthesizer = FeedbackSynthesizer()
        feedback = synthesizer.synthesize(verdicts, _mock_descriptor())

        assert any("semantic-gap:search-relevance" in f for f in feedback.suggested_focus)

    def test_semantic_fail_in_focus(self) -> None:
        verdicts = [
            ScenarioVerdict(
                scenario_id="search-quality",
                scenario_name="Search Quality",
                status="fail",
                steps=[
                    StepVerdict(
                        step_id="search",
                        transport="http",
                        status="fail",
                        semantic_verdict=SemanticVerdict(
                            status="fail",
                            confidence=0.3,
                            reasoning="Results not relevant",
                        ),
                    ),
                ],
                category="memory-crud",
                interfaces_tested=["POST /memory/query"],
            ),
        ]

        synthesizer = FeedbackSynthesizer()
        feedback = synthesizer.synthesize(verdicts, _mock_descriptor())

        assert any("semantic-gap:search-quality" in f for f in feedback.suggested_focus)

    def test_no_semantic_no_gap(self) -> None:
        """Scenarios without semantic blocks produce no semantic gaps."""
        verdicts = [
            ScenarioVerdict(
                scenario_id="simple",
                scenario_name="Simple",
                status="pass",
                steps=[
                    StepVerdict(
                        step_id="s1",
                        transport="http",
                        status="pass",
                    ),
                ],
                category="test",
                interfaces_tested=["GET /health"],
            ),
        ]

        synthesizer = FeedbackSynthesizer()
        feedback = synthesizer.synthesize(verdicts, _mock_descriptor())

        assert not any("semantic-gap" in f for f in feedback.suggested_focus)
