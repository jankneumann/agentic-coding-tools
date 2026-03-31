"""Tests for FeedbackSynthesizer and ChangeDetector.

Covers verdict synthesis, coverage computation, under-tested detection,
near-miss detection, prompt text formatting, git diff change detection,
change-context parsing, and error handling.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from evaluation.gen_eval.change_detector import ChangeDetector
from evaluation.gen_eval.descriptor import (
    EndpointDescriptor,
    FileInterfaceMapping,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
    ToolDescriptor,
)
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.models import EvalFeedback, ScenarioVerdict, StepVerdict

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def descriptor() -> InterfaceDescriptor:
    """Descriptor with 4 interfaces across 2 services."""
    return InterfaceDescriptor(
        project="test-project",
        version="0.1.0",
        services=[
            ServiceDescriptor(
                name="api",
                type="http",
                base_url="http://localhost:8081",
                endpoints=[
                    EndpointDescriptor(path="/locks/acquire", method="POST"),
                    EndpointDescriptor(path="/locks/release", method="POST"),
                    EndpointDescriptor(path="/health", method="GET"),
                ],
            ),
            ServiceDescriptor(
                name="mcp",
                type="mcp",
                transport="sse",
                mcp_url="http://localhost:8082/sse",
                tools=[
                    ToolDescriptor(name="acquire_lock"),
                ],
            ),
        ],
        state_verifiers=[],
        startup=StartupConfig(
            command="echo start",
            health_check="http://localhost:8081/health",
            teardown="echo stop",
        ),
        file_interface_map=[
            FileInterfaceMapping(
                file_pattern="src/locks.py",
                interfaces=["POST /locks/acquire", "POST /locks/release"],
            ),
            FileInterfaceMapping(
                file_pattern="src/mcp_*.py",
                interfaces=["mcp:acquire_lock"],
            ),
        ],
    )


def _make_verdict(
    scenario_id: str,
    status: str,
    category: str,
    interfaces_tested: list[str],
    duration_seconds: float = 0.1,
    steps: list[StepVerdict] | None = None,
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Test: {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=steps or [],
        duration_seconds=duration_seconds,
        interfaces_tested=interfaces_tested,
        category=category,
    )


def _make_step(
    step_id: str,
    status: str,
    duration_ms: float = 10.0,
    diff: dict | None = None,
) -> StepVerdict:
    return StepVerdict(
        step_id=step_id,
        transport="http",
        status=status,  # type: ignore[arg-type]
        duration_ms=duration_ms,
        diff=diff,
    )


# ---------------------------------------------------------------------------
# FeedbackSynthesizer tests
# ---------------------------------------------------------------------------


class TestFeedbackSynthesizer:
    def test_synthesize_with_mixed_verdicts(self, descriptor: InterfaceDescriptor) -> None:
        """Test with a mix of pass/fail/error verdicts."""
        verdicts = [
            _make_verdict(
                "s1",
                "fail",
                "locks",
                ["POST /locks/acquire"],
                steps=[_make_step("step1", "fail")],
            ),
            _make_verdict("s2", "pass", "locks", ["POST /locks/release"]),
            _make_verdict("s3", "error", "health", ["GET /health"]),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert feedback.iteration == 1
        assert "POST /locks/acquire" in feedback.failing_interfaces

    def test_failing_interfaces_from_step_fail(self, descriptor: InterfaceDescriptor) -> None:
        """Failing interfaces are collected from steps with status=fail."""
        verdicts = [
            _make_verdict(
                "s1",
                "fail",
                "locks",
                ["POST /locks/acquire", "POST /locks/release"],
                steps=[
                    _make_step("step1", "pass"),
                    _make_step("step2", "fail"),
                ],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert sorted(feedback.failing_interfaces) == [
            "POST /locks/acquire",
            "POST /locks/release",
        ]

    def test_no_failing_when_all_pass(self, descriptor: InterfaceDescriptor) -> None:
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"]),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)
        assert feedback.failing_interfaces == []

    def test_coverage_calculation(self, descriptor: InterfaceDescriptor) -> None:
        """Coverage summary shows 100% for exercised, 0% for not."""
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"]),
            _make_verdict("s2", "pass", "locks", ["GET /health"]),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        # 4 total interfaces; 2 exercised
        assert feedback.coverage_summary["POST /locks/acquire"] == 100.0
        assert feedback.coverage_summary["GET /health"] == 100.0
        assert feedback.coverage_summary["POST /locks/release"] == 0.0
        assert feedback.coverage_summary["mcp:acquire_lock"] == 0.0

    def test_under_tested_detection(self, descriptor: InterfaceDescriptor) -> None:
        """Categories with fewer scenarios than 50% of total interfaces are under-tested."""
        # 4 total interfaces, so need >= 2 scenarios per category to not be under-tested
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"]),
            # Only 1 scenario in 'locks', 1/4 = 25% < 50%
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "locks" in feedback.under_tested_categories

    def test_not_under_tested_with_enough_scenarios(self, descriptor: InterfaceDescriptor) -> None:
        """Category with enough scenarios should not be under-tested."""
        # 4 interfaces, need >= 2 scenarios
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"]),
            _make_verdict("s2", "pass", "locks", ["POST /locks/release"]),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "locks" not in feedback.under_tested_categories

    def test_under_tested_uses_interfaces_not_scenarios(
        self, descriptor: InterfaceDescriptor
    ) -> None:
        """Under-tested metric uses interfaces exercised, not scenario count."""
        # 4 total interfaces. Two scenarios in 'locks' but both test the same interface.
        # interfaces_exercised_in_category = 1, ratio = 1/4 = 25% < 50%
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"]),
            _make_verdict("s2", "pass", "locks", ["POST /locks/acquire"]),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "locks" in feedback.under_tested_categories

    def test_near_miss_high_latency(self, descriptor: InterfaceDescriptor) -> None:
        """Passed scenarios with duration > 500ms are near-miss."""
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"], duration_seconds=0.8),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "s1" in feedback.near_miss_scenarios

    def test_near_miss_with_diff(self, descriptor: InterfaceDescriptor) -> None:
        """Passed scenarios with step diffs are near-miss."""
        verdicts = [
            _make_verdict(
                "s1",
                "pass",
                "locks",
                ["POST /locks/acquire"],
                steps=[_make_step("step1", "pass", diff={"body.count": "expected 5, got 4"})],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "s1" in feedback.near_miss_scenarios

    def test_no_near_miss_for_failed(self, descriptor: InterfaceDescriptor) -> None:
        """Failed scenarios should not appear as near-miss."""
        verdicts = [
            _make_verdict(
                "s1",
                "fail",
                "locks",
                ["POST /locks/acquire"],
                duration_seconds=1.0,
                steps=[_make_step("step1", "fail")],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "s1" not in feedback.near_miss_scenarios

    def test_near_miss_skips_latency_when_duration_zero(
        self, descriptor: InterfaceDescriptor
    ) -> None:
        """duration_seconds=0.0 means timing was not set; latency near-miss should be skipped."""
        verdicts = [
            _make_verdict("s1", "pass", "locks", ["POST /locks/acquire"], duration_seconds=0.0),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        # Should NOT be near-miss from latency alone (0.0 means unset)
        assert "s1" not in feedback.near_miss_scenarios

    def test_near_miss_zero_duration_with_diff_still_detected(
        self, descriptor: InterfaceDescriptor
    ) -> None:
        """Even with duration_seconds=0.0, partial diffs should trigger near-miss."""
        verdicts = [
            _make_verdict(
                "s1",
                "pass",
                "locks",
                ["POST /locks/acquire"],
                duration_seconds=0.0,
                steps=[_make_step("step1", "pass", diff={"body.x": "expected 1, got 2"})],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        # Should still be near-miss because of the diff
        assert "s1" in feedback.near_miss_scenarios

    def test_near_miss_not_triggered_by_empty_diff(self, descriptor: InterfaceDescriptor) -> None:
        """Empty diff dict should not trigger near-miss."""
        verdicts = [
            _make_verdict(
                "s1",
                "pass",
                "locks",
                ["POST /locks/acquire"],
                duration_seconds=0.1,
                steps=[_make_step("step1", "pass", diff={})],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        assert "s1" not in feedback.near_miss_scenarios

    def test_suggested_focus_combines_failing_and_under_tested(
        self, descriptor: InterfaceDescriptor
    ) -> None:
        """Suggested focus is the union of failing interfaces and under-tested categories."""
        verdicts = [
            _make_verdict(
                "s1",
                "fail",
                "locks",
                ["POST /locks/acquire"],
                steps=[_make_step("step1", "fail")],
            ),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)

        # "POST /locks/acquire" from failing, "locks" from under-tested
        assert "POST /locks/acquire" in feedback.suggested_focus
        assert "locks" in feedback.suggested_focus

    def test_iteration_increments_from_previous(self, descriptor: InterfaceDescriptor) -> None:
        prev = EvalFeedback(iteration=3)
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([], descriptor, previous_feedback=prev)
        assert feedback.iteration == 4

    def test_first_iteration_without_previous(self, descriptor: InterfaceDescriptor) -> None:
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([], descriptor, previous_feedback=None)
        assert feedback.iteration == 1

    def test_to_prompt_text_readable(self, descriptor: InterfaceDescriptor) -> None:
        """to_prompt_text produces a readable multi-line string."""
        verdicts = [
            _make_verdict(
                "s1",
                "fail",
                "locks",
                ["POST /locks/acquire"],
                steps=[_make_step("step1", "fail")],
            ),
            _make_verdict("s2", "pass", "health", ["GET /health"], duration_seconds=0.8),
        ]
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize(verdicts, descriptor)
        text = synth.to_prompt_text(feedback)

        assert "Evaluation Feedback (iteration 1)" in text
        assert "Failing interfaces:" in text
        assert "POST /locks/acquire" in text
        assert "Near-miss scenarios" in text
        assert "s2" in text
        assert "Coverage summary:" in text
        assert "Suggested focus" in text

    def test_to_prompt_text_empty_feedback(self, descriptor: InterfaceDescriptor) -> None:
        """Empty feedback still produces a header."""
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([], descriptor)
        text = synth.to_prompt_text(feedback)
        assert "iteration 1" in text

    def test_empty_descriptor_no_crash(self) -> None:
        """No interfaces in descriptor should not crash."""
        empty_descriptor = InterfaceDescriptor(
            project="empty",
            version="0.1.0",
            services=[],
            startup=StartupConfig(command="echo", health_check="http://localhost", teardown="echo"),
        )
        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([], empty_descriptor)
        assert feedback.coverage_summary == {}
        assert feedback.under_tested_categories == []


# ---------------------------------------------------------------------------
# ChangeDetector tests
# ---------------------------------------------------------------------------


class TestChangeDetector:
    def test_git_diff_maps_files_to_interfaces(self, descriptor: InterfaceDescriptor) -> None:
        """Changed files matching patterns should map to interfaces."""
        detector = ChangeDetector(descriptor)

        mock_result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "src/locks.py\nsrc/unrelated.py\n",
                "stderr": "",
            },
        )()

        with patch(
            "evaluation.gen_eval.change_detector.subprocess.run", return_value=mock_result
        ) as mock_run:
            result = detector.detect_from_git_diff("main")

        # Verify merge-base comparison syntax (base_ref...HEAD)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "diff", "--name-only", "main...HEAD"]

        assert "POST /locks/acquire" in result
        assert "POST /locks/release" in result

    def test_git_diff_glob_pattern(self, descriptor: InterfaceDescriptor) -> None:
        """Glob patterns like src/mcp_*.py should match."""
        detector = ChangeDetector(descriptor)

        mock_result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "src/mcp_server.py\n",
                "stderr": "",
            },
        )()

        with patch("evaluation.gen_eval.change_detector.subprocess.run", return_value=mock_result):
            result = detector.detect_from_git_diff("main")

        assert "mcp:acquire_lock" in result

    def test_git_diff_no_matches(self, descriptor: InterfaceDescriptor) -> None:
        """Files that don't match any pattern return empty list."""
        detector = ChangeDetector(descriptor)

        mock_result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "README.md\ndocs/guide.md\n",
                "stderr": "",
            },
        )()

        with patch("evaluation.gen_eval.change_detector.subprocess.run", return_value=mock_result):
            result = detector.detect_from_git_diff("main")

        assert result == []

    def test_git_diff_subprocess_failure(self, descriptor: InterfaceDescriptor) -> None:
        """Subprocess errors should return empty list."""
        detector = ChangeDetector(descriptor)

        with patch(
            "evaluation.gen_eval.change_detector.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            result = detector.detect_from_git_diff("main")

        assert result == []

    def test_git_diff_nonzero_return_code(self, descriptor: InterfaceDescriptor) -> None:
        """Non-zero return code returns empty list."""
        detector = ChangeDetector(descriptor)

        mock_result = type(
            "Result",
            (),
            {
                "returncode": 128,
                "stdout": "",
                "stderr": "fatal: not a git repo",
            },
        )()

        with patch("evaluation.gen_eval.change_detector.subprocess.run", return_value=mock_result):
            result = detector.detect_from_git_diff("main")

        assert result == []

    def test_change_context_parsing(self, descriptor: InterfaceDescriptor, tmp_path: Path) -> None:
        """Parses change-context.md and maps file references to interfaces."""
        ctx = tmp_path / "change-context.md"
        ctx.write_text("# Changes\n\n- Modified `src/locks.py` for lock timeout\n- Updated tests\n")

        detector = ChangeDetector(descriptor)
        result = detector.detect_from_change_context(ctx)

        assert "POST /locks/acquire" in result
        assert "POST /locks/release" in result

    def test_change_context_missing_file(
        self, descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        """Missing change-context.md returns empty list."""
        detector = ChangeDetector(descriptor)
        result = detector.detect_from_change_context(tmp_path / "nonexistent.md")
        assert result == []

    def test_change_context_no_matching_files(
        self, descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        """Change context with no file patterns returns empty."""
        ctx = tmp_path / "change-context.md"
        ctx.write_text("# Changes\n\nJust some notes about the feature.\n")

        detector = ChangeDetector(descriptor)
        result = detector.detect_from_change_context(ctx)
        assert result == []

    def test_empty_file_interface_map(self) -> None:
        """Descriptor with no file_interface_map returns empty."""
        desc = InterfaceDescriptor(
            project="test",
            version="0.1.0",
            services=[],
            startup=StartupConfig(command="echo", health_check="http://localhost", teardown="echo"),
            file_interface_map=[],
        )
        detector = ChangeDetector(desc)

        mock_result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "src/locks.py\n",
                "stderr": "",
            },
        )()

        with patch("evaluation.gen_eval.change_detector.subprocess.run", return_value=mock_result):
            result = detector.detect_from_git_diff("main")

        assert result == []
