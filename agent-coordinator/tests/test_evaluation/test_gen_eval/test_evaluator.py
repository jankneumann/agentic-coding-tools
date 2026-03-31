"""Tests for the Evaluator module."""

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
    method: str = "POST",
    endpoint: str = "/test",
    body: dict[str, Any] | None = None,
    expect: ExpectBlock | None = None,
    capture: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> ActionStep:
    return ActionStep(
        id=step_id,
        transport=transport,
        method=method,
        endpoint=endpoint,
        body=body or {},
        expect=expect,
        capture=capture,
        timeout_seconds=timeout_seconds,
    )


def _make_scenario(
    scenario_id: str = "test-scenario",
    steps: list[ActionStep] | None = None,
    cleanup: list[ActionStep] | None = None,
) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=f"Test: {scenario_id}",
        description="A test scenario",
        category="test",
        priority=1,
        interfaces=["http"],
        steps=steps or [],
        cleanup=cleanup,
    )


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
    error: str | None = None,
    exit_code: int | None = None,
    duration_ms: float = 10.0,
) -> StepResult:
    return StepResult(
        status_code=status_code,
        body=body or {},
        error=error,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )


def _mock_registry(*results: StepResult) -> TransportClientRegistry:
    """Create a mock registry that returns results sequentially."""
    registry = MagicMock(spec=TransportClientRegistry)
    registry.execute = AsyncMock(side_effect=list(results))
    return registry


def _mock_descriptor() -> InterfaceDescriptor:
    """Create a minimal mock descriptor."""
    return MagicMock(spec=InterfaceDescriptor)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicExecution:
    """Basic step execution and pass verdict."""

    @pytest.mark.asyncio
    async def test_single_step_pass(self) -> None:
        result = _make_result(status_code=200, body={"success": True})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200, body={"success": True}))
        scenario = _make_scenario(steps=[step])

        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        assert verdict.scenario_id == "test-scenario"
        assert len(verdict.steps) == 1
        assert verdict.steps[0].status == "pass"
        assert verdict.steps[0].step_id == "step1"

    @pytest.mark.asyncio
    async def test_empty_scenario(self) -> None:
        """Empty scenario (no steps) should produce pass verdict."""
        registry = _mock_registry()
        evaluator = Evaluator(_mock_descriptor(), registry)

        scenario = _make_scenario(steps=[])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        assert len(verdict.steps) == 0

    @pytest.mark.asyncio
    async def test_step_without_expectations(self) -> None:
        """Step with no expect block should pass if no transport error."""
        result = _make_result(status_code=200, body={"data": "ok"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=None)
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        assert verdict.steps[0].status == "pass"


class TestStepFailure:
    """Step failure with diff reporting."""

    @pytest.mark.asyncio
    async def test_status_mismatch_fails(self) -> None:
        result = _make_result(status_code=500, body={"error": "server error"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "fail"
        assert verdict.steps[0].status == "fail"
        assert verdict.steps[0].diff is not None
        assert verdict.steps[0].diff["status"]["expected"] == 200
        assert verdict.steps[0].diff["status"]["actual"] == 500

    @pytest.mark.asyncio
    async def test_body_mismatch_fails(self) -> None:
        result = _make_result(status_code=200, body={"success": False})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200, body={"success": True}))
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "fail"
        assert verdict.steps[0].diff is not None
        assert "body" in verdict.steps[0].diff

    @pytest.mark.asyncio
    async def test_failure_summary_present(self) -> None:
        result = _make_result(status_code=404)
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(step_id="my_step", expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.failure_summary is not None
        assert "my_step" in verdict.failure_summary


class TestVariableCapture:
    """Variable capture from JSONPath."""

    @pytest.mark.asyncio
    async def test_capture_simple_jsonpath(self) -> None:
        result = _make_result(body={"task_id": "abc-123", "status": "created"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            capture={"task_id": "$.task_id"},
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        assert verdict.steps[0].captured_vars is not None
        assert verdict.steps[0].captured_vars["task_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_capture_nested_jsonpath(self) -> None:
        result = _make_result(body={"data": {"id": 42, "name": "test"}})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            capture={"item_id": "$.data.id"},
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.steps[0].captured_vars is not None
        assert verdict.steps[0].captured_vars["item_id"] == 42

    @pytest.mark.asyncio
    async def test_capture_no_match_returns_none(self) -> None:
        result = _make_result(body={"other": "value"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            capture={"missing": "$.nonexistent"},
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        assert verdict.steps[0].captured_vars["missing"] is None


class TestVariableInterpolation:
    """Variable interpolation in subsequent steps."""

    @pytest.mark.asyncio
    async def test_interpolation_in_endpoint(self) -> None:
        result1 = _make_result(body={"id": "res-99"})
        result2 = _make_result(body={"deleted": True})
        registry = _mock_registry(result1, result2)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step1 = _make_step(
            step_id="create",
            capture={"resource_id": "$.id"},
            expect=ExpectBlock(status=200),
        )
        step2 = _make_step(
            step_id="delete",
            endpoint="/resources/{{ resource_id }}",
            method="DELETE",
            expect=ExpectBlock(status=200, body={"deleted": True}),
        )
        scenario = _make_scenario(steps=[step1, step2])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        # Verify that the endpoint was interpolated
        call_args = registry.execute.call_args_list[1]
        executed_step = call_args[0][1]  # second positional arg is the step
        assert executed_step.endpoint == "/resources/res-99"

    @pytest.mark.asyncio
    async def test_interpolation_in_body(self) -> None:
        result1 = _make_result(body={"token": "xyz"})
        result2 = _make_result(body={"ok": True})
        registry = _mock_registry(result1, result2)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step1 = _make_step(
            step_id="auth",
            capture={"auth_token": "$.token"},
            expect=ExpectBlock(status=200),
        )
        step2 = _make_step(
            step_id="use",
            body={"token": "{{ auth_token }}"},
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step1, step2])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "pass"
        call_args = registry.execute.call_args_list[1]
        executed_step = call_args[0][1]
        assert executed_step.body["token"] == "xyz"

    @pytest.mark.asyncio
    async def test_interpolation_with_hyphens_and_dots(self) -> None:
        """Variables with hyphens and dots should interpolate correctly."""
        result = _make_result(body={"ok": True})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            endpoint="/items/{{ my-var.name }}",
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        # Provide a variable with hyphens and dots
        # We need to manually set captured_vars context
        await evaluator.evaluate(scenario)

        # Check the step was called with the unresolved var (no context vars)
        call_args = registry.execute.call_args_list[0]
        executed_step = call_args[0][1]
        assert executed_step.endpoint == "/items/{{ my-var.name }}"

        # Now test with actual variable resolution
        result2 = _make_result(body={"id": "val-1"})
        result3 = _make_result(body={"ok": True})
        registry2 = _mock_registry(result2, result3)
        evaluator2 = Evaluator(_mock_descriptor(), registry2)

        step1 = _make_step(
            step_id="create",
            capture={"my-var.name": "$.id"},
            expect=ExpectBlock(status=200),
        )
        step2 = _make_step(
            step_id="use",
            endpoint="/items/{{ my-var.name }}",
            expect=ExpectBlock(status=200),
        )
        scenario2 = _make_scenario(steps=[step1, step2])
        await evaluator2.evaluate(scenario2)

        call_args2 = registry2.execute.call_args_list[1]
        executed_step2 = call_args2[0][1]
        assert executed_step2.endpoint == "/items/val-1"

    @pytest.mark.asyncio
    async def test_unresolved_variable_kept_as_is(self) -> None:
        """Variables not in context stay as literal {{ var }} strings."""
        result = _make_result(body={"ok": True})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            endpoint="/items/{{ unknown_var }}",
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        await evaluator.evaluate(scenario)

        call_args = registry.execute.call_args_list[0]
        executed_step = call_args[0][1]
        assert executed_step.endpoint == "/items/{{ unknown_var }}"


class TestInvalidJsonPath:
    """Invalid JSONPath produces error verdict, not crash."""

    @pytest.mark.asyncio
    async def test_invalid_capture_jsonpath(self) -> None:
        result = _make_result(body={"data": "value"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            capture={"bad": "[[[invalid"},
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "error"
        assert verdict.steps[0].status == "error"
        assert "Invalid JSONPath" in (verdict.steps[0].error_message or "")

    @pytest.mark.asyncio
    async def test_invalid_body_jsonpath_assertion(self) -> None:
        result = _make_result(body={"data": "value"})
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            expect=ExpectBlock(status=200, body={"$[[[bad": "value"}),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "fail"
        assert verdict.steps[0].diff is not None
        assert "body" in verdict.steps[0].diff


class TestCleanupSteps:
    """Cleanup steps always run even after failure."""

    @pytest.mark.asyncio
    async def test_cleanup_runs_after_failure(self) -> None:
        fail_result = _make_result(status_code=500)
        cleanup_result = _make_result(status_code=200, body={"cleaned": True})
        registry = _mock_registry(fail_result, cleanup_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        main_step = _make_step(step_id="main", expect=ExpectBlock(status=200))
        cleanup_step = _make_step(step_id="cleanup")
        scenario = _make_scenario(steps=[main_step], cleanup=[cleanup_step])

        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "fail"
        # 1 main step + 1 cleanup step
        assert len(verdict.steps) == 2
        assert verdict.steps[1].is_cleanup is True
        # Registry should have been called twice (main + cleanup)
        assert registry.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_failure_is_warning_not_status_change(self) -> None:
        main_result = _make_result(status_code=200, body={"ok": True})
        cleanup_result = _make_result(status_code=500, error="cleanup failed")
        registry = _mock_registry(main_result, cleanup_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        main_step = _make_step(step_id="main", expect=ExpectBlock(status=200, body={"ok": True}))
        cleanup_step = _make_step(step_id="cleanup")
        scenario = _make_scenario(steps=[main_step], cleanup=[cleanup_step])

        verdict = await evaluator.evaluate(scenario)

        # Overall status should still be pass
        assert verdict.status == "pass"
        assert len(verdict.cleanup_warnings) == 1
        assert "cleanup" in verdict.cleanup_warnings[0]

    @pytest.mark.asyncio
    async def test_cleanup_failure_preserves_original_status(self) -> None:
        """L1: Cleanup step verdict should keep its original failure status for debugging."""
        main_result = _make_result(status_code=200, body={"ok": True})
        cleanup_result = _make_result(status_code=500, error="cleanup failed")
        registry = _mock_registry(main_result, cleanup_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        main_step = _make_step(step_id="main", expect=ExpectBlock(status=200, body={"ok": True}))
        cleanup_step = _make_step(step_id="cleanup")
        scenario = _make_scenario(steps=[main_step], cleanup=[cleanup_step])

        verdict = await evaluator.evaluate(scenario)

        # Overall scenario should still pass (cleanup doesn't taint it)
        assert verdict.status == "pass"
        # But the cleanup step verdict should retain its original error status
        cleanup_verdict = [v for v in verdict.steps if v.is_cleanup][0]
        assert cleanup_verdict.status == "error"
        assert cleanup_verdict.is_cleanup is True


class TestStepTimeout:
    """Step timeout produces error verdict."""

    @pytest.mark.asyncio
    async def test_timeout_produces_error(self) -> None:
        async def slow_execute(*args: Any, **kwargs: Any) -> StepResult:
            await asyncio.sleep(10)
            return _make_result()

        registry = MagicMock(spec=TransportClientRegistry)
        registry.execute = AsyncMock(side_effect=slow_execute)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(timeout_seconds=1, expect=ExpectBlock(status=200))
        # Use a very short timeout
        scenario = _make_scenario(steps=[step])

        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "error"
        assert verdict.steps[0].status == "error"
        assert "timed out" in (verdict.steps[0].error_message or "").lower()


class TestCrossInterfaceMismatch:
    """Cross-interface mismatch detection."""

    @pytest.mark.asyncio
    async def test_detects_mismatch_across_transports(self) -> None:
        http_result = _make_result(body={"name": "Alice", "role": "admin"})
        mcp_result = _make_result(body={"name": "Alice", "role": "user"})
        registry = _mock_registry(http_result, mcp_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step_http = _make_step(
            step_id="http_get",
            transport="http",
            expect=ExpectBlock(status=200),
        )
        step_mcp = _make_step(
            step_id="mcp_get",
            transport="mcp",
            expect=ExpectBlock(status=200),
        )
        scenario = _make_scenario(steps=[step_http, step_mcp])
        scenario.interfaces = ["http", "mcp"]
        verdict = await evaluator.evaluate(scenario)

        # REQ-EVAL-03: cross-interface mismatch MUST be reported as "fail"
        assert verdict.status == "fail"
        mcp_verdict = verdict.steps[1]
        assert mcp_verdict.status == "fail"
        assert mcp_verdict.diff is not None
        cross = mcp_verdict.diff
        # Check for the cross-interface mismatch structure
        assert "cross_interface_mismatch" in cross or "cross_interface" in cross

    @pytest.mark.asyncio
    async def test_no_mismatch_same_transport(self) -> None:
        result1 = _make_result(body={"val": 1})
        result2 = _make_result(body={"val": 2})
        registry = _mock_registry(result1, result2)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step1 = _make_step(step_id="s1", transport="http", expect=ExpectBlock(status=200))
        step2 = _make_step(step_id="s2", transport="http", expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step1, step2])
        verdict = await evaluator.evaluate(scenario)

        # Same transport -> no cross-interface diff
        assert verdict.steps[1].diff is None


class TestSkipAfterFailure:
    """Skip remaining steps after first failure."""

    @pytest.mark.asyncio
    async def test_remaining_steps_skipped(self) -> None:
        fail_result = _make_result(status_code=500)
        registry = _mock_registry(fail_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step1 = _make_step(step_id="s1", expect=ExpectBlock(status=200))
        step2 = _make_step(step_id="s2", expect=ExpectBlock(status=200))
        step3 = _make_step(step_id="s3", expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step1, step2, step3])

        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "fail"
        assert verdict.steps[0].status == "fail"
        assert verdict.steps[1].status == "skip"
        assert verdict.steps[2].status == "skip"
        # Only one call to registry (skipped steps don't execute)
        assert registry.execute.call_count == 1


class TestBatchEvaluation:
    """Batch evaluation of multiple scenarios."""

    @pytest.mark.asyncio
    async def test_batch_evaluates_all(self) -> None:
        result1 = _make_result(body={"ok": True})
        result2 = _make_result(body={"ok": True})
        registry = _mock_registry(result1, result2)
        evaluator = Evaluator(_mock_descriptor(), registry)

        s1 = _make_scenario(
            scenario_id="s1",
            steps=[_make_step(step_id="a", expect=ExpectBlock(status=200, body={"ok": True}))],
        )
        s2 = _make_scenario(
            scenario_id="s2",
            steps=[_make_step(step_id="b", expect=ExpectBlock(status=200, body={"ok": True}))],
        )
        verdicts = await evaluator.evaluate_batch([s1, s2])

        assert len(verdicts) == 2
        assert verdicts[0].scenario_id == "s1"
        assert verdicts[1].scenario_id == "s2"
        assert all(v.status == "pass" for v in verdicts)

    @pytest.mark.asyncio
    async def test_batch_empty_list(self) -> None:
        registry = _mock_registry()
        evaluator = Evaluator(_mock_descriptor(), registry)

        verdicts = await evaluator.evaluate_batch([])
        assert verdicts == []


class TestTransportError:
    """Transport-level errors produce error verdicts."""

    @pytest.mark.asyncio
    async def test_transport_error_in_result(self) -> None:
        result = _make_result(error="Connection refused")
        registry = _mock_registry(result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "error"
        assert verdict.steps[0].status == "error"
        assert "Connection refused" in (verdict.steps[0].error_message or "")

    @pytest.mark.asyncio
    async def test_transport_exception(self) -> None:
        registry = MagicMock(spec=TransportClientRegistry)
        registry.execute = AsyncMock(side_effect=RuntimeError("boom"))
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(expect=ExpectBlock(status=200))
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.status == "error"
        assert "Transport error" in (verdict.steps[0].error_message or "")


class TestExtractInterfaces:
    """Test endpoint-specific interface extraction from scenario steps."""

    def test_http_step_produces_method_path(self) -> None:
        steps = [ActionStep(id="s1", transport="http", method="POST", endpoint="/locks/acquire")]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["POST /locks/acquire"]

    def test_mcp_step_produces_mcp_prefix(self) -> None:
        steps = [ActionStep(id="s1", transport="mcp", tool="check_locks")]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["mcp:check_locks"]

    def test_cli_step_produces_cli_prefix_with_subcommand(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", command="lock status --file-path x")]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["cli:lock status"]

    def test_db_and_wait_omitted(self) -> None:
        steps = [
            ActionStep(id="s1", transport="db", sql="SELECT 1"),
            ActionStep(id="s2", transport="wait", seconds=1.0),
        ]
        result = Evaluator._extract_interfaces(steps)
        assert result == []

    def test_deduplicates(self) -> None:
        steps = [
            ActionStep(id="s1", transport="http", method="POST", endpoint="/locks/acquire"),
            ActionStep(id="s2", transport="http", method="POST", endpoint="/locks/acquire"),
        ]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["POST /locks/acquire"]

    def test_mixed_transports(self) -> None:
        steps = [
            ActionStep(id="s1", transport="http", method="POST", endpoint="/locks/acquire"),
            ActionStep(id="s2", transport="mcp", tool="check_locks"),
            ActionStep(id="s3", transport="cli", command="lock status --file-path x"),
            ActionStep(id="s4", transport="db", sql="SELECT 1"),
        ]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["POST /locks/acquire", "mcp:check_locks", "cli:lock status"]

    def test_cli_base_command_without_subcommand(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", command="guardrails")]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["cli:guardrails"]

    def test_http_strips_query_string(self) -> None:
        steps = [ActionStep(id="s1", transport="http", method="GET", endpoint="/audit?limit=10")]
        result = Evaluator._extract_interfaces(steps)
        assert result == ["GET /audit"]

    @pytest.mark.asyncio
    async def test_evaluate_produces_endpoint_specific_interfaces(self) -> None:
        """End-to-end: evaluator verdict has endpoint-specific interfaces_tested."""
        ok_result = _make_result(body={"success": True})
        registry = _mock_registry(ok_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        step = _make_step(
            step_id="s1",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            expect=ExpectBlock(status=200, body={"success": True}),
        )
        scenario = _make_scenario(steps=[step])
        verdict = await evaluator.evaluate(scenario)

        assert verdict.interfaces_tested == ["POST /locks/acquire"]
