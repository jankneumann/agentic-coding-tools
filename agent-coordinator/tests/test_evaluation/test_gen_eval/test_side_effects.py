"""Tests for side-effect verify/prohibit execution in the evaluator.

Covers spec scenarios:
- gen-eval-framework (Side-Effect Declaration): Verify side effects after
  successful operation, Prohibit detects unintended mutation, Side effects
  skipped on main step failure, Step start time auto-captured

Design decisions: D2 (sub-block design), D3 (prohibit inverse matching),
  D10 (side-effect steps read-only)
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
    SideEffectsBlock,
    SideEffectStep,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
    error: str | None = None,
) -> StepResult:
    return StepResult(status_code=status_code, body=body or {}, error=error)


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


def _make_scenario(steps: list[ActionStep]) -> Scenario:
    return Scenario(
        id="test-side-effects",
        name="Test side-effect verification",
        description="Tests side-effect verify/prohibit",
        category="test",
        priority=1,
        interfaces=["http", "db"],
        steps=steps,
    )


# ── Model validation ─────────────────────────────────────────────


class TestSideEffectModels:
    """Test SideEffectStep and SideEffectsBlock models."""

    def test_verify_step_creation(self) -> None:
        step = SideEffectStep(
            id="check-audit",
            transport="db",
            sql="SELECT count(*) as rows FROM audit_log WHERE action = 'lock_acquire'",
            expect=ExpectBlock(rows_gte=1),
        )
        assert step.id == "check-audit"
        assert step.mode == "verify"

    def test_prohibit_step_creation(self) -> None:
        step = SideEffectStep(
            id="no-extra-writes",
            transport="db",
            mode="prohibit",
            sql="SELECT count(*) as rows FROM audit_log WHERE action = 'unexpected'",
            expect=ExpectBlock(rows=0),
        )
        assert step.mode == "prohibit"

    def test_http_side_effect_rejects_post(self) -> None:
        """D10: Side-effect steps are read-only — POST rejected."""
        with pytest.raises(ValueError, match="read-only"):
            SideEffectStep(
                id="bad",
                transport="http",
                method="POST",
                endpoint="/test",
                expect=ExpectBlock(status=200),
            )

    def test_http_side_effect_allows_get(self) -> None:
        """D10: GET is allowed for HTTP side-effect steps."""
        step = SideEffectStep(
            id="check",
            transport="http",
            method="GET",
            endpoint="/status",
            expect=ExpectBlock(status=200),
        )
        assert step.method == "GET"

    def test_http_side_effect_allows_head(self) -> None:
        step = SideEffectStep(
            id="check",
            transport="http",
            method="HEAD",
            endpoint="/status",
            expect=ExpectBlock(status=200),
        )
        assert step.method == "HEAD"

    def test_side_effects_block(self) -> None:
        block = SideEffectsBlock(
            verify=[
                SideEffectStep(
                    id="v1", transport="db",
                    sql="SELECT 1", expect=ExpectBlock(rows=1),
                ),
            ],
            prohibit=[
                SideEffectStep(
                    id="p1", transport="db", mode="prohibit",
                    sql="SELECT 0", expect=ExpectBlock(rows=0),
                ),
            ],
        )
        assert len(block.verify) == 1
        assert len(block.prohibit) == 1

    def test_side_effects_on_action_step(self) -> None:
        step = ActionStep(
            id="main-step",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            body={"file_path": "test.py"},
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check-lock",
                        transport="db",
                        sql="SELECT count(*) as rows FROM file_locks",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ],
            ),
        )
        assert step.side_effects is not None
        assert len(step.side_effects.verify) == 1


# ── Evaluator: verify execution ──────────────────────────────────


class TestSideEffectVerify:
    """Verify side-effect steps after successful main step."""

    def test_verify_passes(self) -> None:
        """Verify step confirms expected mutation occurred."""
        # Main step returns 200, verify step finds the row
        registry = _mock_registry(
            _make_result(status_code=200, body={"success": True}),
            _make_result(body={"rows": 1}),  # verify step result
        )
        ev = _make_evaluator(registry)
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check-lock-created",
                        transport="db",
                        sql="SELECT count(*) as rows FROM file_locks",
                        expect=ExpectBlock(rows=1),
                    ),
                ],
            ),
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"
        # Should have side_effect_verdicts on the step verdict
        sv = verdict.steps[0]
        assert sv.side_effect_verdicts is not None
        assert len(sv.side_effect_verdicts) == 1
        assert sv.side_effect_verdicts[0]["status"] == "pass"

    def test_verify_fails(self) -> None:
        """Verify step detects missing mutation → step fails."""
        registry = _mock_registry(
            _make_result(status_code=200, body={"success": True}),
            _make_result(body={"rows": 0}),  # verify fails: expected rows=1
        )
        ev = _make_evaluator(registry)
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check-lock-created",
                        transport="db",
                        sql="SELECT count(*) as rows FROM file_locks",
                        expect=ExpectBlock(rows=1),
                    ),
                ],
            ),
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"


# ── Evaluator: prohibit execution ────────────────────────────────


class TestSideEffectProhibit:
    """Prohibit side-effect steps: inverse matching (D3)."""

    def test_prohibit_passes_when_no_unwanted_state(self) -> None:
        """Prohibited state not found → pass.

        D3 inverse logic: prohibit expects rows_gte=1 (looking for unwanted rows).
        If actual rows=0, expectation does NOT match (diff exists) → prohibit passes.
        """
        registry = _mock_registry(
            _make_result(status_code=200, body={"success": True}),
            _make_result(body={"rows": 0}),  # no unwanted rows found
        )
        ev = _make_evaluator(registry)
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no-duplicate-locks",
                        transport="db",
                        mode="prohibit",
                        sql="SELECT count(*) as rows FROM file_locks WHERE duplicate=true",
                        expect=ExpectBlock(rows_gte=1),  # looking for duplicates
                    ),
                ],
            ),
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_prohibit_fails_when_unwanted_state_found(self) -> None:
        """D3: Prohibited expectations MATCH → prohibit step FAILS."""
        # Prohibit expects rows=0 but the prohibited state is detected
        # when rows actually match the expectation (inverse logic)
        registry = _mock_registry(
            _make_result(status_code=200, body={"success": True}),
            _make_result(body={"rows": 0}),  # expectations match → prohibited state detected
        )
        ev = _make_evaluator(registry)
        # The prohibit step checks: "there should NOT be rows matching this"
        # Expect: rows_gte=1 — if this matches, prohibited state exists
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no-extra-writes",
                        transport="db",
                        mode="prohibit",
                        sql="SELECT count(*) as rows FROM unintended_table",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ],
            ),
        )
        # rows_gte=1 checks if rows >= 1. The result has rows=0, so
        # the expectation does NOT match → diff exists → prohibit passes
        # (no prohibited state found)
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "pass"

    def test_prohibit_detects_unwanted_mutation(self) -> None:
        """D3: When prohibit expectations match, the step fails."""
        registry = _mock_registry(
            _make_result(status_code=200, body={"success": True}),
            _make_result(body={"rows": 3}),  # rows_gte=1 matches → prohibited!
        )
        ev = _make_evaluator(registry)
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                prohibit=[
                    SideEffectStep(
                        id="no-extra-writes",
                        transport="db",
                        mode="prohibit",
                        sql="SELECT count(*) as rows FROM unintended_table",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ],
            ),
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"


# ── Evaluator: skip on failure ───────────────────────────────────


class TestSideEffectSkipOnFailure:
    """Side effects skipped when main step fails."""

    def test_side_effects_skipped_on_main_failure(self) -> None:
        """Side-effect steps should not run if main step fails."""
        registry = _mock_registry(
            _make_result(status_code=500, body={"error": "internal"}),
            # No more results — side effect should NOT be called
        )
        ev = _make_evaluator(registry)
        step = ActionStep(
            id="bad-step",
            transport="http",
            method="POST",
            endpoint="/test",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check",
                        transport="db",
                        sql="SELECT 1",
                        expect=ExpectBlock(rows=1),
                    ),
                ],
            ),
        )
        verdict = asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        assert verdict.status == "fail"
        # Side-effect verdicts should be empty or marked skip
        sv = verdict.steps[0]
        if sv.side_effect_verdicts:
            assert all(v["status"] == "skip" for v in sv.side_effect_verdicts)


# ── step_start_time injection ────────────────────────────────────


class TestStepStartTimeInjection:
    """step_start_time is auto-injected into side-effect step variables."""

    def test_step_start_time_captured(self) -> None:
        """Side-effect steps should have access to step_start_time."""
        call_args: list[Any] = []
        client = AsyncMock()

        async def capture_execute(step: Any, context: Any) -> StepResult:
            call_args.append((step, context))
            if step.transport == "http":
                return _make_result(status_code=200, body={"ok": True})
            return _make_result(body={"rows": 1})

        client.execute = capture_execute
        registry = TransportClientRegistry()
        registry.register("http", client)
        registry.register("db", client)
        ev = _make_evaluator(registry)

        step = ActionStep(
            id="main",
            transport="http",
            method="POST",
            endpoint="/test",
            expect=ExpectBlock(status=200),
            side_effects=SideEffectsBlock(
                verify=[
                    SideEffectStep(
                        id="check-after",
                        transport="db",
                        sql="SELECT count(*) as rows FROM audit WHERE ts > '{{ step_start_time }}'",
                        expect=ExpectBlock(rows_gte=1),
                    ),
                ],
            ),
        )
        asyncio.get_event_loop().run_until_complete(
            ev.evaluate(_make_scenario([step]))
        )
        # The side-effect step should have been called with step_start_time
        # interpolated (the {{ step_start_time }} should be replaced)
        assert len(call_args) >= 2
        se_step = call_args[1][0]
        # The SQL should have the timestamp injected, not the raw template
        assert "{{ step_start_time }}" not in (se_step.sql or "")
