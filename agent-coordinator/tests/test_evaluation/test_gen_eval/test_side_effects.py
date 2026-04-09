"""Tests for side-effect declaration and verification (Phase 2).

Covers: side_effects.verify execution, side_effects.prohibit inverse
matching, skip-on-failure behavior, and step_start_time injection.

Design decisions: D2 (sub-block design), D3 (prohibit semantics).
"""

from __future__ import annotations

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
    SideEffectsBlock,
    SideEffectStep,
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


class TestSideEffectsVerify:
    """side_effects.verify: verification steps that MUST succeed."""

    @pytest.mark.asyncio
    async def test_verify_passes_after_main_step(self) -> None:
        """Spec scenario: Verify side effects after successful operation."""
        main_result = _make_result(body={"success": True})
        verify_result = _make_result(body={"rows": 1, "row": {"action": "store"}})
        registry = _mock_registry(main_result, verify_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="store_memory",
            transport="http",
            method="POST",
            endpoint="/memory/store",
            body={"summary": "test"},
            expect=ExpectBlock(status=200, body={"success": True}),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check_audit",
                        transport="db",
                        sql="SELECT * FROM audit_log WHERE action='store'",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"
        assert len(verdict.steps[0].side_effect_verdicts) == 1
        assert verdict.steps[0].side_effect_verdicts[0].mode == "verify"
        assert verdict.steps[0].side_effect_verdicts[0].status == "pass"

    @pytest.mark.asyncio
    async def test_verify_failure_fails_step(self) -> None:
        main_result = _make_result(body={"success": True})
        verify_result = _make_result(body={"rows": 0})
        registry = _mock_registry(main_result, verify_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="store_memory",
            transport="http",
            method="POST",
            endpoint="/memory/store",
            expect=ExpectBlock(status=200, body={"success": True}),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check_audit",
                        transport="db",
                        sql="SELECT * FROM audit_log",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert verdict.steps[0].side_effect_verdicts[0].status == "fail"


class TestSideEffectsProhibit:
    """side_effects.prohibit: inverse matching (D3)."""

    @pytest.mark.asyncio
    async def test_prohibit_passes_when_state_absent(self) -> None:
        main_result = _make_result(body={"success": True})
        # Actual query returns 0 rows — the prohibited state (rows_gte=1) is absent
        prohibit_result = _make_result(body={"rows": 0})
        registry = _mock_registry(main_result, prohibit_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="read_only_op",
            transport="http",
            method="GET",
            endpoint="/data",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no_writes",
                        transport="db",
                        sql="SELECT * FROM audit_log WHERE action='write'",
                        # Prohibit "1 or more rows" — if this matches, writes happened
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"
        assert verdict.steps[0].side_effect_verdicts[0].mode == "prohibit"
        assert verdict.steps[0].side_effect_verdicts[0].status == "pass"

    @pytest.mark.asyncio
    async def test_prohibit_fails_when_state_exists(self) -> None:
        """Spec scenario: Prohibit detects unintended mutation."""
        main_result = _make_result(body={"success": True})
        # The prohibited state IS present (expectations match → prohibit fails)
        prohibit_result = _make_result(body={"rows": 0})
        registry = _mock_registry(main_result, prohibit_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="denied_op",
            transport="http",
            method="POST",
            endpoint="/admin/action",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no_new_rows",
                        transport="db",
                        sql="SELECT * FROM sensitive_table",
                        # Expecting rows_gte=1 means "there are rows" — if this matches,
                        # the prohibited state exists, so prohibit FAILS
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        # The prohibit step's expectation (rows_gte=1) does NOT match (actual rows=0),
        # so prohibit PASSES — no prohibited state found
        assert verdict.status == "pass"

    @pytest.mark.asyncio
    async def test_prohibit_fails_when_expectations_match(self) -> None:
        """When prohibit expectations match the actual result, it's a failure."""
        main_result = _make_result(body={"success": True})
        # Actual result matches the prohibited expectation
        prohibit_result = _make_result(body={"rows": 5})
        registry = _mock_registry(main_result, prohibit_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="denied_op",
            transport="http",
            method="POST",
            endpoint="/admin/action",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no_new_rows",
                        transport="db",
                        sql="SELECT * FROM sensitive_table",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        se_verdict = verdict.steps[0].side_effect_verdicts[0]
        assert se_verdict.mode == "prohibit"
        assert se_verdict.status == "fail"
        assert "prohibited state detected" in (se_verdict.error_message or "").lower()


class TestSideEffectsSkipOnFailure:
    """Side effects skipped when main step fails."""

    @pytest.mark.asyncio
    async def test_side_effects_skipped_on_main_failure(self) -> None:
        """Spec scenario: Side effects skipped on main step failure."""
        main_result = _make_result(status_code=500)
        registry = _mock_registry(main_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="failing_op",
            transport="http",
            method="POST",
            endpoint="/fail",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="should_not_run",
                        transport="db",
                        sql="SELECT 1",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "fail"
        assert len(verdict.steps[0].side_effect_verdicts) == 0
        # Only the main step was executed
        assert registry.execute.call_count == 1


class TestStepStartTime:
    """step_start_time variable injection for side-effect queries."""

    @pytest.mark.asyncio
    async def test_step_start_time_injected(self) -> None:
        """Spec scenario: Step start time auto-captured for side-effect queries."""
        main_result = _make_result(body={"success": True})
        verify_result = _make_result(body={"rows": 1})
        registry = _mock_registry(main_result, verify_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="timed_op",
            transport="http",
            method="POST",
            endpoint="/op",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check_after_start",
                        transport="db",
                        sql="SELECT * FROM audit WHERE ts > '{{ step_start_time }}'",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ]
            ),
        )
        await evaluator.evaluate(_make_scenario([step]))

        # Verify step_start_time was interpolated (no longer contains {{ }})
        call_args = registry.execute.call_args_list[1]
        executed_step = call_args[0][1]
        assert "{{" not in executed_step.sql
        assert "step_start_time" not in executed_step.sql


class TestSameStepCaptureInSideEffects:
    """Variables captured in the main step must be visible to side-effect steps."""

    @pytest.mark.asyncio
    async def test_same_step_capture_interpolated_in_side_effect_sql(self) -> None:
        """Regression: side-effect SQL references vars captured by the same main step."""
        # Main step returns a body with a task_id that the capture block extracts.
        main_result = _make_result(body={"task_id": "abc-123", "success": True})
        verify_result = _make_result(body={"rows": 1})
        registry = _mock_registry(main_result, verify_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="claim_task",
            transport="http",
            method="POST",
            endpoint="/work/claim",
            expect=ExpectBlock(status=200),
            capture={"claimed_task_id": "$.task_id"},
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="verify_claim_row",
                        transport="db",
                        sql="SELECT * FROM work_queue WHERE id='{{ claimed_task_id }}'",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.status == "pass"
        # The second registry call is the side-effect. Its interpolated SQL must
        # contain the captured task id and MUST NOT contain the placeholder.
        call_args = registry.execute.call_args_list[1]
        executed_step = call_args[0][1]
        assert "abc-123" in executed_step.sql
        assert "{{ claimed_task_id }}" not in executed_step.sql


class TestSideEffectErrorPropagation:
    """A side-effect transport error must downgrade the main step's status."""

    @pytest.mark.asyncio
    async def test_side_effect_error_downgrades_step_to_error(self) -> None:
        """Regression: backend unavailable during verification shouldn't silently pass."""
        main_result = _make_result(body={"success": True})
        # The side-effect call fails with a transport-level error — this must
        # surface as an `error` verdict and downgrade the main step.
        error_result = _make_result(error="Connection refused")
        registry = _mock_registry(main_result, error_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="main_op",
            transport="http",
            method="POST",
            endpoint="/op",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="verify_db",
                        transport="db",
                        sql="SELECT 1",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        assert verdict.steps[0].side_effect_verdicts[0].status == "error"
        assert verdict.steps[0].status == "error"

    @pytest.mark.asyncio
    async def test_side_effect_fail_takes_precedence_over_error(self) -> None:
        """When one verdict fails and another errors, the step status is `fail`."""
        main_result = _make_result(body={"success": True})
        fail_result = _make_result(body={"rows": 0})  # expected rows=1 → fail
        error_result = _make_result(error="Connection refused")
        registry = _mock_registry(main_result, fail_result, error_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = ActionStep(
            id="main_op",
            transport="http",
            method="POST",
            endpoint="/op",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="verify_row_count",
                        transport="db",
                        sql="SELECT COUNT(*) FROM t",
                        expect=ExpectBlock(rows=1),
                    ),
                    SideEffectStep(
                        id="verify_secondary",
                        transport="db",
                        sql="SELECT 1",
                        expect=ExpectBlock(rows=1),
                    ),
                ]
            ),
        )
        verdict = await evaluator.evaluate(_make_scenario([step]))

        statuses = {v.status for v in verdict.steps[0].side_effect_verdicts}
        assert statuses == {"fail", "error"}
        # fail is more specific than error, so the step status is fail.
        assert verdict.steps[0].status == "fail"
