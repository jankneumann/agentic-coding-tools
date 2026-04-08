"""Tests for semantic LLM-as-judge evaluation (Phase 3).

Covers: semantic evaluation invocation, confidence thresholds,
LLM unavailability handling, and semantic verdict reporting.

Design decision: D4 (semantic independence).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.gen_eval.clients.base import StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    SemanticBlock,
)


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
) -> StepResult:
    return StepResult(status_code=status_code, body=body or {})


def _mock_registry(*results: StepResult) -> TransportClientRegistry:
    registry = MagicMock(spec=TransportClientRegistry)
    registry.execute = AsyncMock(side_effect=list(results))
    return registry


def _mock_descriptor() -> InterfaceDescriptor:
    return MagicMock(spec=InterfaceDescriptor)


def _make_scenario(steps: list[ActionStep]) -> Scenario:
    return Scenario(
        id="test",
        name="Test",
        description="Test scenario",
        category="test",
        priority=1,
        interfaces=["http"],
        steps=steps,
    )


class TestSemanticEvaluation:
    """Semantic evaluation with LLM-as-judge."""

    @pytest.mark.asyncio
    async def test_semantic_pass_with_high_confidence(self) -> None:
        """Spec scenario: Semantic evaluation judges search relevance."""
        result = _make_result(
            body={
                "memories": [
                    {"summary": "Q2 project deadlines are approaching"},
                    {"summary": "Sprint review scheduled for Friday"},
                ]
            }
        )
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        mock_judgment = {
            "verdict": "pass",
            "confidence": 0.85,
            "reasoning": "Results are relevant to project deadlines",
        }

        step = ActionStep(
            id="search",
            transport="http",
            method="POST",
            endpoint="/memory/query",
            expect=ExpectBlock(status=200),
            semantic=SemanticBlock(
                judge=True,
                criteria="Results should be relevant to project deadlines",
                fields=["$.memories[*].summary"],
            ),
        )

        with patch(
            "evaluation.gen_eval.evaluator.semantic_judge_evaluate",
            new_callable=AsyncMock,
            return_value=mock_judgment,
        ):
            verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"
        sv = verdict.steps[0].semantic_verdict
        assert sv is not None
        assert sv.status == "pass"
        assert sv.confidence == 0.85

    @pytest.mark.asyncio
    async def test_semantic_fail_low_confidence(self) -> None:
        """Spec scenario: Low confidence produces semantic failure."""
        result = _make_result(
            body={"memories": [{"summary": "Unrelated meeting notes"}]}
        )
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        mock_judgment = {
            "verdict": "fail",
            "confidence": 0.4,
            "reasoning": "Results not relevant to project deadlines",
        }

        step = ActionStep(
            id="search",
            transport="http",
            method="POST",
            endpoint="/memory/query",
            expect=ExpectBlock(status=200),
            semantic=SemanticBlock(
                judge=True,
                criteria="Results should be relevant to project deadlines",
                min_confidence=0.7,
                fields=["$.memories[*].summary"],
            ),
        )

        with patch(
            "evaluation.gen_eval.evaluator.semantic_judge_evaluate",
            new_callable=AsyncMock,
            return_value=mock_judgment,
        ):
            verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        sv = verdict.steps[0].semantic_verdict
        assert sv is not None
        assert sv.status == "fail"
        assert sv.confidence == 0.4

    @pytest.mark.asyncio
    async def test_semantic_skip_when_llm_unavailable(self) -> None:
        """Spec scenario: Unavailable LLM produces skip, not failure."""
        result = _make_result(body={"data": "ok"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="search",
            transport="http",
            method="POST",
            endpoint="/memory/query",
            expect=ExpectBlock(status=200),
            semantic=SemanticBlock(
                judge=True,
                criteria="Results should be relevant",
            ),
        )

        with patch(
            "evaluation.gen_eval.evaluator.semantic_judge_evaluate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM backend unreachable"),
        ):
            verdict = await evaluator.evaluate(_make_scenario([step]))

        # Overall verdict NOT changed to fail
        assert verdict.status == "pass"
        sv = verdict.steps[0].semantic_verdict
        assert sv is not None
        assert sv.status == "skip"
        assert "unreachable" in sv.reasoning.lower() or "unavailable" in sv.reasoning.lower()

    @pytest.mark.asyncio
    async def test_no_semantic_when_judge_false(self) -> None:
        """No semantic evaluation when judge=False."""
        result = _make_result(body={"data": "ok"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="step",
            transport="http",
            method="GET",
            endpoint="/data",
            expect=ExpectBlock(status=200),
            semantic=SemanticBlock(judge=False, criteria="irrelevant"),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"
        assert verdict.steps[0].semantic_verdict is None

    @pytest.mark.asyncio
    async def test_no_semantic_block_at_all(self) -> None:
        """Step without semantic block has no semantic verdict."""
        result = _make_result(body={"ok": True})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="step",
            transport="http",
            method="GET",
            endpoint="/data",
            expect=ExpectBlock(status=200, body={"ok": True}),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.steps[0].semantic_verdict is None

    @pytest.mark.asyncio
    async def test_semantic_fail_does_not_override_structural_fail(self) -> None:
        """D4: Semantic verdicts never override structural verdicts."""
        result = _make_result(status_code=500)
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="step",
            transport="http",
            method="GET",
            endpoint="/data",
            expect=ExpectBlock(status=200),
            semantic=SemanticBlock(judge=True, criteria="Should succeed"),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        # Status is fail from structural check, semantic not even run
        assert verdict.status == "fail"
        # Semantic should not have run since structural failed
        assert verdict.steps[0].semantic_verdict is None
