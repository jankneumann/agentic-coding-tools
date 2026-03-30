"""Tests for core gen-eval data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evaluation.gen_eval.models import (
    ActionStep,
    EvalFeedback,
    ExpectBlock,
    Scenario,
    ScenarioVerdict,
    StepVerdict,
)


class TestExpectBlock:
    def test_empty(self) -> None:
        block = ExpectBlock()
        assert block.status is None
        assert block.body is None

    def test_http_expect(self) -> None:
        block = ExpectBlock(status=200, body={"success": True})
        assert block.status == 200

    def test_db_expect(self) -> None:
        block = ExpectBlock(rows=1, row={"agent_id": "agent-1"})
        assert block.rows == 1

    def test_error_expect(self) -> None:
        block = ExpectBlock(status=409, error_contains="already locked")
        assert block.error_contains == "already locked"


class TestActionStep:
    def test_http_step(self) -> None:
        step = ActionStep(
            id="acquire",
            transport="http",
            method="POST",
            endpoint="/locks/acquire",
            body={"file_path": "main.py"},
            expect=ExpectBlock(status=200),
        )
        assert step.transport == "http"
        assert step.method == "POST"

    def test_mcp_step(self) -> None:
        step = ActionStep(
            id="mcp_acquire",
            transport="mcp",
            tool="acquire_lock",
            params={"file_path": "main.py"},
        )
        assert step.transport == "mcp"
        assert step.tool == "acquire_lock"

    def test_cli_step(self) -> None:
        step = ActionStep(
            id="cli_lock",
            transport="cli",
            command="lock acquire",
            args=["--file-path", "main.py"],
            expect=ExpectBlock(exit_code=0),
        )
        assert step.transport == "cli"

    def test_db_step(self) -> None:
        step = ActionStep(
            id="verify_db",
            transport="db",
            sql="SELECT * FROM file_locks WHERE file_path = 'main.py'",
            expect=ExpectBlock(rows=1),
        )
        assert step.transport == "db"

    def test_wait_step(self) -> None:
        step = ActionStep(id="wait", transport="wait", seconds=2.0)
        assert step.seconds == 2.0

    def test_capture(self) -> None:
        step = ActionStep(
            id="capture_id",
            transport="http",
            method="POST",
            endpoint="/work/submit",
            capture={"task_id": "$.task_id"},
        )
        assert step.capture is not None
        assert step.capture["task_id"] == "$.task_id"

    def test_invalid_transport(self) -> None:
        with pytest.raises(ValidationError):
            ActionStep(id="bad", transport="invalid")  # type: ignore[arg-type]

    def test_timeout_override(self) -> None:
        step = ActionStep(
            id="slow",
            transport="http",
            method="GET",
            endpoint="/slow",
            timeout_seconds=120,
        )
        assert step.timeout_seconds == 120


class TestScenario:
    def test_basic(self) -> None:
        scenario = Scenario(
            id="test-1",
            name="Test scenario",
            description="A test",
            category="lock-lifecycle",
            priority=1,
            interfaces=["http"],
            steps=[ActionStep(id="s1", transport="http", method="GET", endpoint="/health")],
        )
        assert scenario.category == "lock-lifecycle"
        assert scenario.generated_by == "template"

    def test_with_cleanup(self, sample_scenario: Scenario) -> None:
        assert sample_scenario.cleanup is not None
        assert len(sample_scenario.cleanup) == 1

    def test_with_parameters(self) -> None:
        scenario = Scenario(
            id="param-test",
            name="Parameterized",
            description="Test with params",
            category="test",
            interfaces=["http"],
            steps=[ActionStep(id="s1", transport="http", method="GET", endpoint="/health")],
            parameters={"agent_id": ["agent-1", "agent-2"]},
        )
        assert scenario.parameters is not None
        assert len(scenario.parameters["agent_id"]) == 2

    def test_tags(self) -> None:
        scenario = Scenario(
            id="tagged",
            name="Tagged",
            description="Test tags",
            category="test",
            interfaces=["http"],
            steps=[ActionStep(id="s1", transport="http", method="GET", endpoint="/health")],
            tags=["locks", "basic", "happy-path-only"],
        )
        assert "happy-path-only" in scenario.tags

    def test_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            Scenario(
                id="bad",
                name="Bad",
                description="Missing interfaces",
                category="test",
                # interfaces missing
                steps=[],
            )  # type: ignore[call-arg]


class TestStepVerdict:
    def test_pass(self) -> None:
        verdict = StepVerdict(
            step_id="s1",
            transport="http",
            status="pass",
            actual={"status": 200},
            expected={"status": 200},
            duration_ms=10.0,
        )
        assert verdict.status == "pass"
        assert verdict.diff is None

    def test_fail_with_diff(self) -> None:
        verdict = StepVerdict(
            step_id="s1",
            transport="http",
            status="fail",
            actual={"status": 409},
            expected={"status": 200},
            diff={"status": {"actual": 409, "expected": 200}},
            duration_ms=15.0,
        )
        assert verdict.status == "fail"
        assert verdict.diff is not None

    def test_error(self) -> None:
        verdict = StepVerdict(
            step_id="s1",
            transport="http",
            status="error",
            actual={},
            error_message="Connection refused",
            duration_ms=5000.0,
        )
        assert verdict.error_message == "Connection refused"

    def test_cleanup_flag(self) -> None:
        verdict = StepVerdict(
            step_id="cleanup1",
            transport="http",
            status="fail",
            actual={},
            is_cleanup=True,
        )
        assert verdict.is_cleanup


class TestScenarioVerdict:
    def test_pass(self, sample_scenario_verdict: ScenarioVerdict) -> None:
        assert sample_scenario_verdict.status == "pass"
        assert len(sample_scenario_verdict.steps) == 1

    def test_with_cleanup_warnings(self) -> None:
        verdict = ScenarioVerdict(
            scenario_id="test",
            scenario_name="Test",
            status="pass",
            steps=[],
            cleanup_warnings=["Cleanup step cleanup1 failed: timeout"],
        )
        assert len(verdict.cleanup_warnings) == 1

    def test_fail_summary(self) -> None:
        verdict = ScenarioVerdict(
            scenario_id="test",
            scenario_name="Test",
            status="fail",
            steps=[],
            failure_summary="Step s2 failed: expected 200, got 409",
        )
        assert "409" in (verdict.failure_summary or "")


class TestEvalFeedback:
    def test_basic(self) -> None:
        feedback = EvalFeedback(
            iteration=1,
            failing_interfaces=["POST /locks/acquire"],
            under_tested_categories=["audit-trail"],
            near_miss_scenarios=["lock-ttl-expiry"],
            suggested_focus=["lock contention edge cases"],
        )
        assert feedback.iteration == 1
        assert len(feedback.failing_interfaces) == 1

    def test_empty_first_iteration(self) -> None:
        feedback = EvalFeedback(iteration=0)
        assert feedback.failing_interfaces == []
        assert feedback.under_tested_categories == []

    def test_coverage_summary(self) -> None:
        feedback = EvalFeedback(
            iteration=2,
            coverage_summary={
                "lock-lifecycle": 87.5,
                "auth-boundary": 62.5,
                "work-queue": 40.0,
            },
        )
        assert feedback.coverage_summary["lock-lifecycle"] == 87.5
