"""Tests for semantic evaluation (LLM-as-judge).

Covers spec scenarios:
- gen-eval-framework (Calibrated Noul-Based Semantic Judgment): A confident
  noul produces a pass with zero LLM calls, A low-confidence noul triggers
  reasoning generation, An unavailable decision helper still produces skip
  not fail, judge=False still skips without calling decide() or the backend

Design decisions: D1 (decide() replaces the backend as the confidence
source), D2 (optional system_one_decisions import), D3 (tests use
system_one_decisions.testing.stub_decide)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from system_one_decisions.testing import stub_decide

from gen_eval.models import SemanticBlock
from gen_eval.semantic_judge import _parse_verdict, evaluate_semantic

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_backend(response: str = "") -> AsyncMock:
    """A backend double used only for reasoning-prose generation now --
    evaluate_semantic no longer calls `is_available()` (D1: unavailability is
    detected via decide() returning None, not a backend health check)."""
    backend = AsyncMock()
    backend.run = AsyncMock(return_value=response)
    return backend


def _noul_answers(value: float) -> dict[str, object]:
    """Mimic decide()'s real return shape: `response.answers` keyed by
    question name, with attribute-accessed answer objects (`.noul`), per
    `typesafe_sdk._core.response_types.NoulAnswer`."""
    return {"satisfies": SimpleNamespace(noul=value)}


# ── evaluate_semantic ────────────────────────────────────────────


class TestEvaluateSemantic:
    """Test end-to-end semantic evaluation."""

    async def test_confident_noul_passes_with_zero_llm_calls(self, monkeypatch) -> None:
        stub_decide(monkeypatch, returns=_noul_answers(0.95))
        backend = _mock_backend()
        semantic = SemanticBlock(judge=True, criteria="Is the search relevant?")
        actual = {"results": [{"name": "alice", "score": 0.9}]}

        verdict = await evaluate_semantic(backend, semantic, actual, "search-step")
        assert verdict.status == "pass"
        assert verdict.confidence == 0.95
        backend.run.assert_not_called()

    async def test_low_confidence_noul_triggers_reasoning_generation(self, monkeypatch) -> None:
        stub_decide(monkeypatch, returns=_noul_answers(0.3))
        response = json.dumps({"pass": False, "confidence": 0.8, "reasoning": "Wrong results"})
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True, min_confidence=0.7)

        verdict = await evaluate_semantic(backend, semantic, {"results": []}, "step1")
        assert verdict.status == "fail"
        assert verdict.confidence == 0.3  # noul-derived, not the backend's own 0.8
        assert verdict.reasoning == "Wrong results"
        backend.run.assert_called_once()

    async def test_low_confidence_backend_error_still_fails_with_generic_reasoning(
        self, monkeypatch
    ) -> None:
        """A reasoning-generation failure must not turn a decided `fail` into `skip`."""
        stub_decide(monkeypatch, returns=_noul_answers(0.1))
        backend = AsyncMock()
        backend.run = AsyncMock(side_effect=RuntimeError("connection refused"))
        semantic = SemanticBlock(judge=True)

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "fail"
        assert verdict.confidence == 0.1

    async def test_decide_returns_none_produces_skip(self, monkeypatch) -> None:
        """decide() returning None (any of its own unavailability branches) -> skip."""
        stub_decide(monkeypatch, returns=None)
        backend = _mock_backend()
        semantic = SemanticBlock(judge=True, criteria="Check relevance")

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "skip"
        backend.run.assert_not_called()

    async def test_judge_false_skips(self, monkeypatch) -> None:
        """judge=False -> skip without calling decide() or the backend."""
        stub_decide(monkeypatch, returns=_noul_answers(0.99))
        backend = _mock_backend()
        semantic = SemanticBlock(judge=False)

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "skip"
        backend.run.assert_not_called()

    async def test_markdown_fences_stripped_from_reasoning_response(self, monkeypatch) -> None:
        """A fail-path reasoning response wrapped in markdown fences is still parsed."""
        stub_decide(monkeypatch, returns=_noul_answers(0.2))
        response = '```json\n{"pass": false, "confidence": 0.9, "reasoning": "good catch"}\n```'
        backend = _mock_backend(response)
        semantic = SemanticBlock(judge=True)

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "fail"
        assert verdict.reasoning == "good catch"

    async def test_invalid_reasoning_json_still_fails_with_fallback_reasoning(
        self, monkeypatch
    ) -> None:
        stub_decide(monkeypatch, returns=_noul_answers(0.2))
        backend = _mock_backend("this is not json")
        semantic = SemanticBlock(judge=True)

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "fail"
        assert verdict.confidence == 0.2


class TestEvaluateSemanticWithoutDecisionsExtra:
    """decide() unreachable because system_one_decisions itself isn't installed.

    semantic_judge.py holds its own module-level reference (`None` when the
    import failed, per D2) rather than a bound `decide` name -- patching that
    reference is the unit-test equivalent of the optional extra being absent,
    without needing a real ImportError.
    """

    async def test_module_unavailable_produces_skip(self, monkeypatch) -> None:
        import gen_eval.semantic_judge as module

        monkeypatch.setattr(module, "system_one_decisions", None)
        backend = _mock_backend()
        semantic = SemanticBlock(judge=True)

        verdict = await evaluate_semantic(backend, semantic, {}, "step1")
        assert verdict.status == "skip"
        backend.run.assert_not_called()


# ── _parse_verdict ───────────────────────────────────────────────
#
# Unchanged: _parse_verdict is reused verbatim as a reasoning-text parsing
# helper (design D1); its own unit tests are untouched.


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

    def test_confidence_clamped_high(self) -> None:
        """Confidence > 1.0 is clamped to 1.0."""
        raw = json.dumps({"pass": True, "confidence": 1.5, "reasoning": "Very sure"})
        v = _parse_verdict(raw, 0.7)
        assert v.status == "pass"
        assert v.confidence == 1.0

    def test_confidence_clamped_low(self) -> None:
        """Confidence < 0.0 is clamped to 0.0."""
        raw = json.dumps({"pass": False, "confidence": -0.5, "reasoning": "Confused"})
        v = _parse_verdict(raw, 0.7)
        assert v.confidence == 0.0
