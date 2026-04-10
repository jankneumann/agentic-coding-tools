"""Tests for semantic evaluation (LLM-as-judge).

Covers spec scenarios:
- gen-eval-framework (Semantic Evaluation): Semantic evaluation judges search
  relevance, Low confidence produces semantic failure, Unavailable LLM produces
  skip not failure

Design decisions: D4 (semantic independence), D9 (use existing LLM backend)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from evaluation.gen_eval.models import SemanticBlock, SemanticVerdict
from evaluation.gen_eval.semantic_judge import _parse_verdict, evaluate_semantic

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_backend(response: str, available: bool = True) -> AsyncMock:
    backend = AsyncMock()
    backend.is_available = AsyncMock(return_value=available)
    backend.run = AsyncMock(return_value=response)
    return backend


# ── evaluate_semantic ────────────────────────────────────────────


class TestEvaluateSemantic:
    """Test end-to-end semantic evaluation."""

    def test_pass_with_high_confidence(self) -> None:
        response = json.dumps({"pass": True, "confidence": 0.95, "reasoning": "Looks correct"})
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True, criteria="Is the search relevant?")
        actual = {"results": [{"name": "alice", "score": 0.9}]}

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, actual, "search-step")
        )
        assert verdict.status == "pass"
        assert verdict.confidence == 0.95
        assert verdict.reasoning == "Looks correct"

    def test_fail_when_judge_says_no(self) -> None:
        response = json.dumps({"pass": False, "confidence": 0.8, "reasoning": "Wrong results"})
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True, criteria="Are results relevant?")

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {"results": []}, "step1")
        )
        assert verdict.status == "fail"
        assert verdict.confidence == 0.8

    def test_low_confidence_produces_failure(self) -> None:
        """Low confidence even with pass=True → fail."""
        response = json.dumps({"pass": True, "confidence": 0.3, "reasoning": "Maybe ok"})
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True, min_confidence=0.7)

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "fail"
        assert "Below confidence" in verdict.reasoning

    def test_unavailable_llm_produces_skip(self) -> None:
        """Unavailable LLM → skip, not failure."""
        backend = _mock_backend("", available=False)
        semantic = SemanticBlock(judge=True, criteria="Check relevance")

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "skip"
        assert "unavailable" in verdict.reasoning.lower()

    def test_judge_false_skips(self) -> None:
        """judge=False → skip without calling backend."""
        backend = _mock_backend("")
        semantic = SemanticBlock(judge=False)

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "skip"
        backend.run.assert_not_called()

    def test_backend_error_produces_skip(self) -> None:
        """Backend error → skip, not failure."""
        backend = AsyncMock()
        backend.is_available = AsyncMock(return_value=True)
        backend.run = AsyncMock(side_effect=RuntimeError("connection refused"))
        semantic = SemanticBlock(judge=True)

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "skip"
        assert verdict.error_message is not None

    def test_markdown_fences_stripped(self) -> None:
        """Response wrapped in markdown code fences is still parsed."""
        response = '```json\n{"pass": true, "confidence": 0.9, "reasoning": "good"}\n```'
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True)

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "pass"

    def test_invalid_json_produces_skip(self) -> None:
        backend = _mock_backend("this is not json")
        semantic = SemanticBlock(judge=True)

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluate_semantic(backend, semantic, {}, "step1")
        )
        assert verdict.status == "skip"
        assert "JSON" in (verdict.error_message or verdict.reasoning)


# ── _parse_verdict ───────────────────────────────────────────────


class TestParseVerdict:
    """Test verdict parsing from LLM output."""

    def test_pass(self) -> None:
        raw = json.dumps({"pass": True, "confidence": 0.85, "reasoning": "Correct"})
        v = _parse_verdict(raw, 0.7)
        assert v.status == "pass"
        assert v.confidence == 0.85

    def test_fail(self) -> None:
        raw = json.dumps({"pass": False, "confidence": 0.9, "reasoning": "Wrong"})
        v = _parse_verdict(raw, 0.7)
        assert v.status == "fail"

    def test_below_threshold(self) -> None:
        raw = json.dumps({"pass": True, "confidence": 0.5, "reasoning": "Unsure"})
        v = _parse_verdict(raw, 0.7)
        assert v.status == "fail"

    def test_invalid_json(self) -> None:
        v = _parse_verdict("not json at all", 0.7)
        assert v.status == "skip"

    def test_missing_fields_defaults(self) -> None:
        raw = json.dumps({})
        v = _parse_verdict(raw, 0.7)
        # pass defaults to False → fail
        assert v.status == "fail"
