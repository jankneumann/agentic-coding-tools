"""Tests for extended assertion types on ExpectBlock.

Covers spec scenarios:
- gen-eval-framework (Extended Assertion Types): body_contains, body_excludes,
  status_one_of, rows_gte, rows_lte, array_contains
- Mutual exclusion: status and status_one_of cannot both be set

Design decisions: D1 (extend ExpectBlock), D5 (deep matching algorithm)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from evaluation.gen_eval.clients.base import StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    step_id: str = "step1",
    transport: str = "http",
    method: str = "GET",
    endpoint: str = "/test",
    expect: ExpectBlock | None = None,
) -> ActionStep:
    return ActionStep(
        id=step_id,
        transport=transport,
        method=method,
        endpoint=endpoint,
        expect=expect,
    )


def _make_scenario(steps: list[ActionStep]) -> Scenario:
    return Scenario(
        id="test-extended",
        name="Test extended assertions",
        description="Tests extended assertion types",
        category="test",
        priority=1,
        interfaces=["http"],
        steps=steps,
    )


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
) -> StepResult:
    return StepResult(status_code=status_code, body=body or {})


def _mock_registry(*results: StepResult) -> TransportClientRegistry:
    registry = TransportClientRegistry()
    client = AsyncMock()
    client.execute = AsyncMock(side_effect=list(results))
    registry.register("http", client)
    registry.register("db", client)
    return registry


def _make_evaluator(registry: TransportClientRegistry) -> Evaluator:
    descriptor = MagicMock(spec=InterfaceDescriptor)
    descriptor.all_interfaces.return_value = []
    return Evaluator(descriptor=descriptor, clients=registry)


# ── Model validation ─────────────────────────────────────────────


class TestExpectBlockExtended:
    """Test new ExpectBlock fields and mutual exclusion."""

    def test_body_contains_field(self) -> None:
        eb = ExpectBlock(body_contains={"status": "ok"})
        assert eb.body_contains == {"status": "ok"}

    def test_body_excludes_field(self) -> None:
        eb = ExpectBlock(body_excludes={"error": "forbidden"})
        assert eb.body_excludes == {"error": "forbidden"}

    def test_status_one_of_field(self) -> None:
        eb = ExpectBlock(status_one_of=[200, 201])
        assert eb.status_one_of == [200, 201]

    def test_rows_gte_field(self) -> None:
        eb = ExpectBlock(rows_gte=5)
        assert eb.rows_gte == 5

    def test_rows_lte_field(self) -> None:
        eb = ExpectBlock(rows_lte=10)
        assert eb.rows_lte == 10

    def test_array_contains_field(self) -> None:
        eb = ExpectBlock(array_contains=[{"name": "alice"}])
        assert eb.array_contains == [{"name": "alice"}]

    def test_status_and_status_one_of_mutually_exclusive(self) -> None:
        """status and status_one_of cannot both be set."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            ExpectBlock(status=200, status_one_of=[200, 201])

    def test_backward_compatibility(self) -> None:
        """Existing fields still work."""
        eb = ExpectBlock(status=200, body={"ok": True}, rows=3)
        assert eb.status == 200
        assert eb.body == {"ok": True}
        assert eb.rows == 3

    def test_all_new_fields_optional(self) -> None:
        """All new fields default to None."""
        eb = ExpectBlock()
        assert eb.body_contains is None
        assert eb.body_excludes is None
        assert eb.status_one_of is None
        assert eb.rows_gte is None
        assert eb.rows_lte is None
        assert eb.array_contains is None


# ── Evaluator: body_contains ─────────────────────────────────────


class TestBodyContains:
    """body_contains: deep recursive subset matching (D5)."""

    def test_flat_match(self) -> None:
        registry = _mock_registry(
            _make_result(body={"status": "ok", "count": 5, "extra": True})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_contains={"status": "ok", "count": 5}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_nested_dict_match(self) -> None:
        registry = _mock_registry(
            _make_result(body={"data": {"user": {"name": "alice", "role": "admin"}, "id": 1}})
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(body_contains={"data": {"user": {"name": "alice"}}})
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_flat_mismatch(self) -> None:
        registry = _mock_registry(
            _make_result(body={"status": "error"})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_contains={"status": "ok"}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_missing_key(self) -> None:
        registry = _mock_registry(
            _make_result(body={"other": "value"})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_contains={"status": "ok"}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_list_subset_match(self) -> None:
        """Expected list items must each match a distinct actual item."""
        registry = _mock_registry(
            _make_result(body={"items": [{"id": 1}, {"id": 2}, {"id": 3}]})
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(body_contains={"items": [{"id": 1}, {"id": 3}]})
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_list_no_match(self) -> None:
        registry = _mock_registry(
            _make_result(body={"items": [{"id": 1}, {"id": 2}]})
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(body_contains={"items": [{"id": 99}]})
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"


# ── Evaluator: body_excludes ─────────────────────────────────────


class TestBodyExcludes:
    """body_excludes: negative assertion — body must NOT contain these."""

    def test_excluded_field_absent(self) -> None:
        registry = _mock_registry(
            _make_result(body={"status": "ok"})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_excludes={"error": "forbidden"}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_excluded_field_present(self) -> None:
        registry = _mock_registry(
            _make_result(body={"error": "forbidden", "status": "fail"})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_excludes={"error": "forbidden"}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_excluded_value_different(self) -> None:
        """Key exists but with different value — passes."""
        registry = _mock_registry(
            _make_result(body={"error": "not_found"})
        )
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(body_excludes={"error": "forbidden"}))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"


# ── Evaluator: status_one_of ─────────────────────────────────────


class TestStatusOneOf:
    """status_one_of: accept any listed status code."""

    def test_matches_first(self) -> None:
        registry = _mock_registry(_make_result(status_code=200))
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(status_one_of=[200, 201]))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_matches_second(self) -> None:
        registry = _mock_registry(_make_result(status_code=201))
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(status_one_of=[200, 201]))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_no_match(self) -> None:
        registry = _mock_registry(_make_result(status_code=500))
        ev = _make_evaluator(registry)
        step = _make_step(expect=ExpectBlock(status_one_of=[200, 201]))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"


# ── Evaluator: rows_gte / rows_lte ───────────────────────────────


class TestRowsRange:
    """rows_gte and rows_lte: range assertions for DB row counts."""

    def test_rows_gte_pass(self) -> None:
        registry = _mock_registry(_make_result(body={"rows": 10}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_gte=5))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_rows_gte_exact(self) -> None:
        registry = _mock_registry(_make_result(body={"rows": 5}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_gte=5))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_rows_gte_fail(self) -> None:
        registry = _mock_registry(_make_result(body={"rows": 2}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_gte=5))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_rows_lte_pass(self) -> None:
        registry = _mock_registry(_make_result(body={"rows": 3}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_lte=5))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_rows_lte_fail(self) -> None:
        registry = _mock_registry(_make_result(body={"rows": 10}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_lte=5))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_rows_gte_and_lte_combined(self) -> None:
        """Both range bounds can be used together."""
        registry = _mock_registry(_make_result(body={"rows": 7}))
        ev = _make_evaluator(registry)
        step = _make_step(transport="db", expect=ExpectBlock(rows_gte=5, rows_lte=10))
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"


# ── Evaluator: array_contains ────────────────────────────────────


class TestArrayContains:
    """array_contains: assert response array has matching elements."""

    def test_single_match(self) -> None:
        registry = _mock_registry(
            _make_result(body={"items": [{"name": "alice"}, {"name": "bob"}]})
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(
                array_contains=[{"path": "$.items", "match": {"name": "alice"}}]
            )
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_no_match(self) -> None:
        registry = _mock_registry(
            _make_result(body={"items": [{"name": "alice"}]})
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(
                array_contains=[{"path": "$.items", "match": {"name": "charlie"}}]
            )
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"

    def test_multiple_array_contains(self) -> None:
        """Multiple array_contains entries must all pass."""
        registry = _mock_registry(
            _make_result(body={
                "users": [{"name": "alice"}, {"name": "bob"}],
                "roles": [{"role": "admin"}, {"role": "viewer"}],
            })
        )
        ev = _make_evaluator(registry)
        step = _make_step(
            expect=ExpectBlock(
                array_contains=[
                    {"path": "$.users", "match": {"name": "bob"}},
                    {"path": "$.roles", "match": {"role": "admin"}},
                ]
            )
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"
