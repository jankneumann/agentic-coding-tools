"""Tests for extended report generation (Phase 6).

Covers: side-effect sub-verdict reporting, semantic confidence in reports,
and visibility-grouped reporting.
"""

from __future__ import annotations

from evaluation.gen_eval.models import (
    ScenarioVerdict,
    SemanticVerdict,
    SideEffectVerdict,
    StepVerdict,
)
from evaluation.gen_eval.reports import (
    GenEvalReport,
    generate_markdown_report,
)


def _sample_report_with_side_effects() -> GenEvalReport:
    """Create a report with side-effect verdicts and semantic verdicts."""
    step1 = StepVerdict(
        step_id="store_memory",
        transport="http",
        status="pass",
        actual={"status": 200, "body": {"success": True}},
        expected={"status": 200},
        duration_ms=45.0,
        side_effect_verdicts=[
            SideEffectVerdict(
                step_id="check_audit",
                mode="verify",
                status="pass",
                actual={"body": {"rows": 1}},
            ),
            SideEffectVerdict(
                step_id="no_working_mem",
                mode="prohibit",
                status="pass",
                actual={"body": {"rows": 0}},
            ),
        ],
        semantic_verdict=SemanticVerdict(
            status="pass",
            confidence=0.92,
            reasoning="Results match criteria",
        ),
    )
    step2 = StepVerdict(
        step_id="query_memory",
        transport="http",
        status="fail",
        actual={"status": 200, "body": {}},
        duration_ms=30.0,
        side_effect_verdicts=[
            SideEffectVerdict(
                step_id="check_audit_query",
                mode="verify",
                status="fail",
                actual={"body": {"rows": 0}},
                diff={"rows": {"expected": 1, "actual": 0}},
            ),
        ],
    )

    verdict = ScenarioVerdict(
        scenario_id="memory-lifecycle-e2e",
        scenario_name="Memory lifecycle E2E",
        status="fail",
        steps=[step1, step2],
        duration_seconds=0.075,
        interfaces_tested=["POST /memory/store", "POST /memory/query"],
        category="memory-crud",
        failure_summary="Step 'query_memory' fail: side-effect check_audit_query failed",
    )

    return GenEvalReport(
        total_scenarios=1,
        passed=0,
        failed=1,
        errors=0,
        skipped=0,
        pass_rate=0.0,
        coverage_pct=50.0,
        duration_seconds=0.075,
        budget_exhausted=False,
        verdicts=[verdict],
        per_interface={
            "POST /memory/store": {"pass": 1, "fail": 0, "error": 0},
            "POST /memory/query": {"pass": 0, "fail": 1, "error": 0},
        },
        per_category={"memory-crud": {"total": 1, "pass": 0, "fail": 1, "error": 0}},
        unevaluated_interfaces=["GET /health"],
        cost_summary={"cli_calls": 0, "time_minutes": 0.1, "sdk_cost_usd": 0.0},
        iterations_completed=1,
    )


class TestSideEffectReporting:
    """Side-effect verdicts in report output."""

    def test_markdown_includes_side_effect_details(self) -> None:
        report = _sample_report_with_side_effects()
        md = generate_markdown_report(report)

        assert "Side-Effect" in md or "side_effect" in md.lower() or "Side Effect" in md
        assert "check_audit_query" in md

    def test_markdown_includes_semantic_confidence(self) -> None:
        report = _sample_report_with_side_effects()
        md = generate_markdown_report(report)

        assert "Semantic" in md or "semantic" in md.lower()
        assert "0.92" in md or "92" in md


class TestVisibilityReporting:
    """Visibility-grouped sections in reports."""

    def test_markdown_report_with_visibility(self) -> None:
        """When visibility data is present, report should include it."""
        report = _sample_report_with_side_effects()
        # Add visibility data
        report.visibility_summary = {
            "public": {"total": 5, "passed": 4, "failed": 1},
            "holdout": {"total": 2, "passed": 2, "failed": 0},
        }
        md = generate_markdown_report(report)

        assert "Visibility" in md or "visibility" in md.lower()
        assert "public" in md.lower()
        assert "holdout" in md.lower()
