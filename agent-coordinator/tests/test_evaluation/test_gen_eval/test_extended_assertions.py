"""Tests for extended assertion types (Phase 1).

Covers: body_contains, body_excludes, status_one_of, rows_gte, rows_lte,
array_contains, and status/status_one_of mutual exclusion.

Design decisions: D1 (extend ExpectBlock), D5 (deep matching algorithm).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from evaluation.gen_eval.clients.base import StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.models import ActionStep, ExpectBlock, Scenario


def _make_step(
    step_id: str = "step1",
    transport: str = "http",
    method: str = "POST",
    endpoint: str = "/test",
    body: dict[str, Any] | None = None,
    expect: ExpectBlock | None = None,
) -> ActionStep:
    return ActionStep(
        id=step_id,
        transport=transport,
        method=method,
        endpoint=endpoint,
        body=body or {},
        expect=expect,
    )


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


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
    error: str | None = None,
) -> StepResult:
    return StepResult(status_code=status_code, body=body or {}, error=error)


def _mock_registry(*results: StepResult) -> TransportClientRegistry:
    registry = MagicMock(spec=TransportClientRegistry)
    registry.execute = AsyncMock(side_effect=list(results))
    return registry


def _mock_descriptor() -> InterfaceDescriptor:
    return MagicMock(spec=InterfaceDescriptor)


# ---------------------------------------------------------------------------
# body_contains: deep partial matching (D5)
# ---------------------------------------------------------------------------


class TestBodyContains:
    """body_contains: recursive subset matching."""

    @pytest.mark.asyncio
    async def test_flat_subset_passes(self) -> None:
        result = _make_result(body={"a": 1, "b": 2, "c": 3})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200, body_contains={"a": 1, "b": 2}))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_nested_dict_subset_passes(self) -> None:
        result = _make_result(body={"data": {"id": 1, "name": "test", "extra": True}})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(body_contains={"data": {"id": 1, "name": "test"}}))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_list_subset_passes(self) -> None:
        """Spec scenario: body_contains matches partial structure."""
        result = _make_result(
            body={
                "entries": [
                    {"agent_id": "agent-1", "ts": "2024-01-01"},
                    {"agent_id": "agent-2"},
                ],
                "total": 2,
            }
        )
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(body_contains={"entries": [{"agent_id": "agent-1"}]})
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_missing_key_fails(self) -> None:
        result = _make_result(body={"a": 1})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(body_contains={"b": 2}))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert verdict.steps[0].diff is not None
        assert "body_contains" in verdict.steps[0].diff

    @pytest.mark.asyncio
    async def test_wrong_value_fails(self) -> None:
        result = _make_result(body={"a": 1})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(body_contains={"a": 99}))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"

    @pytest.mark.asyncio
    async def test_list_item_not_found_fails(self) -> None:
        result = _make_result(body={"items": [{"id": 1}, {"id": 2}]})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(body_contains={"items": [{"id": 99}]}))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"


# ---------------------------------------------------------------------------
# body_excludes: negative assertion
# ---------------------------------------------------------------------------


class TestBodyExcludes:
    """body_excludes: body must NOT contain these values."""

    @pytest.mark.asyncio
    async def test_absent_content_passes(self) -> None:
        result = _make_result(body={"entries": [{"agent_id": "agent-1"}]})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(body_excludes={"entries": [{"agent_id": "agent-secret"}]})
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_present_content_fails(self) -> None:
        """Spec scenario: body_excludes detects unwanted content."""
        result = _make_result(body={"entries": [{"agent_id": "agent-secret"}]})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(body_excludes={"entries": [{"agent_id": "agent-secret"}]})
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert verdict.steps[0].diff is not None
        assert "body_excludes" in verdict.steps[0].diff


# ---------------------------------------------------------------------------
# status_one_of
# ---------------------------------------------------------------------------


class TestStatusOneOf:
    """status_one_of: accept multiple valid HTTP status codes."""

    @pytest.mark.asyncio
    async def test_matching_code_passes(self) -> None:
        """Spec scenario: status_one_of accepts any listed code."""
        result = _make_result(status_code=422)
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status_one_of=[200, 422]))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_non_matching_code_fails(self) -> None:
        result = _make_result(status_code=500)
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status_one_of=[200, 201]))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert verdict.steps[0].diff is not None
        assert "status_one_of" in verdict.steps[0].diff

    def test_mutual_exclusion_with_status(self) -> None:
        """Spec scenario: status and status_one_of are mutually exclusive."""
        with pytest.raises(ValidationError, match="mutually exclusive"):
            ExpectBlock(status=200, status_one_of=[200, 201])


# ---------------------------------------------------------------------------
# rows_gte / rows_lte
# ---------------------------------------------------------------------------


class TestRowsRange:
    """rows_gte and rows_lte: row count range assertions."""

    @pytest.mark.asyncio
    async def test_rows_gte_passes(self) -> None:
        """Spec scenario: rows_gte validates minimum row count."""
        result = _make_result(body={"rows": 5})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(rows_gte=3))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_rows_gte_exact_passes(self) -> None:
        result = _make_result(body={"rows": 3})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(rows_gte=3))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_rows_gte_fails(self) -> None:
        result = _make_result(body={"rows": 2})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(rows_gte=3))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"

    @pytest.mark.asyncio
    async def test_rows_lte_passes(self) -> None:
        result = _make_result(body={"rows": 3})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(rows_lte=5))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_rows_lte_fails(self) -> None:
        result = _make_result(body={"rows": 10})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(rows_lte=5))
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"


# ---------------------------------------------------------------------------
# array_contains
# ---------------------------------------------------------------------------


class TestArrayContains:
    """array_contains: assert a JSON array has a matching element."""

    @pytest.mark.asyncio
    async def test_matching_element_passes(self) -> None:
        """Spec scenario: array_contains matches element in array."""
        result = _make_result(
            body={
                "memories": [
                    {"id": 1, "tags": ["deadlines", "q2"]},
                    {"id": 2, "tags": ["meetings"]},
                ]
            }
        )
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(
                array_contains={
                    "path": "$.memories",
                    "match": {"tags": ["deadlines"]},
                }
            )
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_no_matching_element_fails(self) -> None:
        result = _make_result(
            body={
                "memories": [
                    {"id": 1, "tags": ["meetings"]},
                    {"id": 2, "tags": ["meetings"]},
                ]
            }
        )
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(
                array_contains={
                    "path": "$.memories",
                    "match": {"tags": ["deadlines"]},
                }
            )
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert "array_contains" in verdict.steps[0].diff

    @pytest.mark.asyncio
    async def test_invalid_path_fails(self) -> None:
        result = _make_result(body={"data": []})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(
                array_contains={"path": "$[[[bad", "match": {"id": 1}}
            )
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert "array_contains" in verdict.steps[0].diff
