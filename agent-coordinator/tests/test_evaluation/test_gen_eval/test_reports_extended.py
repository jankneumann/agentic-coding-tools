"""Tests for extended report generation with side-effect sub-verdicts and semantic scores.

Design decisions: D2 (side-effect sub-verdicts), D4 (semantic confidence)
"""

from __future__ import annotations

from evaluation.gen_eval.models import ScenarioVerdict, SemanticVerdict, StepVerdict
from evaluation.gen_eval.reports import GenEvalReport, generate_markdown_report


def _make_step_verdict(
    step_id: str = "step1",
    status: str = "pass",
    side_effect_verdicts: list[dict[str, object]] | None = None,
    semantic_verdict: SemanticVerdict | None = None,
) -> StepVerdict:
    return StepVerdict(
        step_id=step_id,
        transport="http",
        status=status,  # type: ignore[arg-type]
        actual={"body": {}},
        side_effect_verdicts=side_effect_verdicts,
        semantic_verdict=semantic_verdict,
    )


def _make_scenario_verdict(
    scenario_id: str = "test",
    status: str = "pass",
    steps: list[StepVerdict] | None = None,
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Test: {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=steps or [],
        interfaces_tested=["http"],
        category="test",
    )


class TestExtendedReports:
    """Test that reports include side-effect and semantic data."""

    def test_report_includes_side_effect_verdicts(self) -> None:
        steps = [
            _make_step_verdict(
                side_effect_verdicts=[
                    {"step_id": "check-audit", "mode": "verify", "status": "pass"},
                    {"step_id": "no-extras", "mode": "prohibit", "status": "pass"},
                ]
            )
        ]
        verdict = _make_scenario_verdict(steps=steps)
        report = GenEvalReport(
            total_scenarios=1, passed=1, failed=0, errors=0, skipped=0,
            pass_rate=1.0, coverage_pct=100.0, duration_seconds=1.0,
            budget_exhausted=False, verdicts=[verdict],
            per_interface={}, per_category={}, unevaluated_interfaces=[],
            cost_summary={}, iterations_completed=1,
        )
        # The step verdicts should be accessible in the report
        assert report.verdicts[0].steps[0].side_effect_verdicts is not None
        assert len(report.verdicts[0].steps[0].side_effect_verdicts) == 2

    def test_report_includes_semantic_verdict(self) -> None:
        steps = [
            _make_step_verdict(
                semantic_verdict=SemanticVerdict(
                    status="pass", confidence=0.92, reasoning="Looks correct"
                )
            )
        ]
        verdict = _make_scenario_verdict(steps=steps)
        report = GenEvalReport(
            total_scenarios=1, passed=1, failed=0, errors=0, skipped=0,
            pass_rate=1.0, coverage_pct=100.0, duration_seconds=1.0,
            budget_exhausted=False, verdicts=[verdict],
            per_interface={}, per_category={}, unevaluated_interfaces=[],
            cost_summary={}, iterations_completed=1,
        )
        sv = report.verdicts[0].steps[0].semantic_verdict
        assert sv is not None
        assert sv.confidence == 0.92

    def test_markdown_report_renders_side_effect_counts(self) -> None:
        steps = [
            _make_step_verdict(
                side_effect_verdicts=[
                    {"step_id": "v1", "mode": "verify", "status": "pass"},
                    {"step_id": "p1", "mode": "prohibit", "status": "fail"},
                ]
            )
        ]
        verdict = _make_scenario_verdict(scenario_id="se-test", status="fail", steps=steps)
        report = GenEvalReport(
            total_scenarios=1, passed=0, failed=1, errors=0, skipped=0,
            pass_rate=0.0, coverage_pct=100.0, duration_seconds=1.0,
            budget_exhausted=False, verdicts=[verdict],
            per_interface={}, per_category={}, unevaluated_interfaces=[],
            cost_summary={}, iterations_completed=1,
        )
        md = generate_markdown_report(report)
        assert "Failed Scenarios" in md
        assert "se-test" in md
