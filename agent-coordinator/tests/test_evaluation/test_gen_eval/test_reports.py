"""Tests for gen-eval report generation."""

from __future__ import annotations

import json

from evaluation.gen_eval.models import ScenarioVerdict
from evaluation.gen_eval.reports import (
    GenEvalReport,
    generate_json_report,
    generate_markdown_report,
)


def _make_verdict(
    scenario_id: str = "s1",
    status: str = "pass",
    interfaces: list[str] | None = None,
    category: str = "locks",
    duration: float = 0.5,
    failure_summary: str | None = None,
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Scenario {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=[],
        duration_seconds=duration,
        interfaces_tested=interfaces or ["POST /locks/acquire"],
        category=category,
        failure_summary=failure_summary,
    )


def _make_report(
    verdicts: list[ScenarioVerdict] | None = None,
    budget_exhausted: bool = False,
) -> GenEvalReport:
    if verdicts is None:
        verdicts = [
            _make_verdict("s1", "pass", ["POST /locks/acquire"], "locks"),
            _make_verdict(
                "s2", "fail", ["POST /locks/release"], "locks", failure_summary="step failed"
            ),
            _make_verdict("s3", "error", ["GET /health"], "health"),
            _make_verdict("s4", "pass", ["POST /locks/acquire"], "locks"),
        ]

    passed = sum(1 for v in verdicts if v.status == "pass")
    failed = sum(1 for v in verdicts if v.status == "fail")
    errors = sum(1 for v in verdicts if v.status == "error")
    skipped = sum(1 for v in verdicts if v.status == "skip")
    total = len(verdicts)

    # Per-interface
    per_interface: dict[str, dict] = {}
    for v in verdicts:
        for iface in v.interfaces_tested:
            if iface not in per_interface:
                per_interface[iface] = {"pass": 0, "fail": 0, "error": 0}
            if v.status in per_interface[iface]:
                per_interface[iface][v.status] += 1

    # Per-category
    per_category: dict[str, dict] = {}
    for v in verdicts:
        cat = v.category or "uncategorized"
        if cat not in per_category:
            per_category[cat] = {"pass": 0, "fail": 0, "error": 0, "total": 0}
        per_category[cat]["total"] += 1
        if v.status in ("pass", "fail", "error"):
            per_category[cat][v.status] += 1

    all_interfaces = {
        "POST /locks/acquire",
        "POST /locks/release",
        "GET /health",
        "mcp:acquire_lock",
        "mcp:release_lock",
        "cli:lock",
    }
    tested = set()
    for v in verdicts:
        tested.update(v.interfaces_tested)
    unevaluated = sorted(all_interfaces - tested)

    coverage_pct = len(tested & all_interfaces) / len(all_interfaces) * 100

    return GenEvalReport(
        total_scenarios=total,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        pass_rate=passed / total if total > 0 else 0.0,
        coverage_pct=coverage_pct,
        duration_seconds=10.5,
        budget_exhausted=budget_exhausted,
        verdicts=verdicts,
        per_interface=per_interface,
        per_category=per_category,
        unevaluated_interfaces=unevaluated,
        cost_summary={"cli_calls": 10.0, "time_minutes": 5.5, "sdk_cost_usd": 1.23},
        iterations_completed=2,
    )


class TestMarkdownReport:
    """Test markdown report generation."""

    def test_markdown_contains_summary(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "# Gen-Eval Report" in md
        assert "**Total scenarios**: 4" in md
        assert "**Passed**: 2" in md
        assert "**Failed**: 1" in md
        assert "**Errors**: 1" in md
        assert "**Pass rate**: 50.0%" in md

    def test_markdown_contains_cost_summary(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "## Cost Summary" in md
        assert "**CLI calls**: 10" in md
        assert "5.5 minutes" in md
        assert "$1.23" in md

    def test_markdown_contains_per_interface(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "## Per-Interface Results" in md
        assert "POST /locks/acquire" in md

    def test_markdown_contains_per_category(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "## Per-Category Results" in md
        assert "locks" in md
        assert "health" in md

    def test_markdown_contains_unevaluated(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "## Unevaluated Interfaces" in md
        assert "mcp:acquire_lock" in md

    def test_markdown_contains_failed_scenarios(self) -> None:
        report = _make_report()
        md = generate_markdown_report(report)

        assert "## Failed Scenarios" in md
        assert "Scenario s2" in md
        assert "step failed" in md

    def test_markdown_budget_exhausted(self) -> None:
        report = _make_report(budget_exhausted=True)
        md = generate_markdown_report(report)

        assert "**Budget exhausted**: True" in md

    def test_markdown_empty_report(self) -> None:
        report = _make_report(verdicts=[])
        md = generate_markdown_report(report)

        assert "**Total scenarios**: 0" in md
        assert "Per-Interface" not in md
        assert "Failed Scenarios" not in md


class TestJsonReport:
    """Test JSON report generation."""

    def test_json_is_valid(self) -> None:
        report = _make_report()
        raw = generate_json_report(report)
        data = json.loads(raw)

        assert data["total_scenarios"] == 4
        assert data["passed"] == 2
        assert data["failed"] == 1
        assert data["errors"] == 1

    def test_json_contains_verdicts(self) -> None:
        report = _make_report()
        raw = generate_json_report(report)
        data = json.loads(raw)

        assert len(data["verdicts"]) == 4
        assert data["verdicts"][0]["scenario_id"] == "s1"

    def test_json_budget_exhausted_flag(self) -> None:
        report = _make_report(budget_exhausted=True)
        raw = generate_json_report(report)
        data = json.loads(raw)

        assert data["budget_exhausted"] is True

    def test_json_cost_summary(self) -> None:
        report = _make_report()
        raw = generate_json_report(report)
        data = json.loads(raw)

        assert data["cost_summary"]["cli_calls"] == 10.0
        assert data["cost_summary"]["sdk_cost_usd"] == 1.23


class TestCoverageCalculation:
    """Test coverage percentage calculation."""

    def test_coverage_pct(self) -> None:
        report = _make_report()
        # 3 interfaces tested out of 6 total = 50%
        assert report.coverage_pct == 50.0

    def test_zero_coverage(self) -> None:
        report = _make_report(verdicts=[])
        assert report.coverage_pct == 0.0


class TestPerInterfaceAggregation:
    """Test per-interface result aggregation."""

    def test_per_interface_counts(self) -> None:
        report = _make_report()

        assert "POST /locks/acquire" in report.per_interface
        assert report.per_interface["POST /locks/acquire"]["pass"] == 2
        assert report.per_interface["POST /locks/release"]["fail"] == 1
        assert report.per_interface["GET /health"]["error"] == 1


class TestPerCategoryAggregation:
    """Test per-category result aggregation."""

    def test_per_category_counts(self) -> None:
        report = _make_report()

        assert "locks" in report.per_category
        assert report.per_category["locks"]["total"] == 3
        assert report.per_category["locks"]["pass"] == 2
        assert report.per_category["locks"]["fail"] == 1
        assert report.per_category["health"]["total"] == 1
        assert report.per_category["health"]["error"] == 1


class TestUnevaluatedInterfaces:
    """Test unevaluated interfaces list."""

    def test_unevaluated_computed_correctly(self) -> None:
        report = _make_report()

        assert "mcp:acquire_lock" in report.unevaluated_interfaces
        assert "mcp:release_lock" in report.unevaluated_interfaces
        assert "cli:lock" in report.unevaluated_interfaces
        # These were tested
        assert "POST /locks/acquire" not in report.unevaluated_interfaces
        assert "GET /health" not in report.unevaluated_interfaces


class TestBudgetExhaustedFlag:
    """Test budget_exhausted flag in report."""

    def test_budget_not_exhausted(self) -> None:
        report = _make_report(budget_exhausted=False)
        assert report.budget_exhausted is False

    def test_budget_exhausted(self) -> None:
        report = _make_report(budget_exhausted=True)
        assert report.budget_exhausted is True

    def test_budget_in_json_report(self) -> None:
        report = _make_report(budget_exhausted=True)
        data = json.loads(generate_json_report(report))
        assert data["budget_exhausted"] is True

    def test_budget_in_markdown_report(self) -> None:
        report = _make_report(budget_exhausted=True)
        md = generate_markdown_report(report)
        assert "True" in md


class TestToMetrics:
    """Test GenEvalReport.to_metrics() integration with evaluation.metrics."""

    def test_converts_verdicts_to_metrics(self) -> None:
        report = _make_report()
        metrics = report.to_metrics()

        assert len(metrics) == 4
        assert metrics[0].scenario_id == "s1"
        assert metrics[0].interface == "POST /locks/acquire"
        assert metrics[0].verdict == "pass"
        assert metrics[1].verdict == "fail"
        assert metrics[2].verdict == "error"
        assert metrics[2].interface == "GET /health"

    def test_empty_report_produces_empty_metrics(self) -> None:
        report = _make_report(verdicts=[])
        metrics = report.to_metrics()
        assert metrics == []

    def test_metrics_have_to_dict(self) -> None:
        report = _make_report()
        metrics = report.to_metrics()
        d = metrics[0].to_dict()
        assert d["scenario_id"] == "s1"
        assert d["interface"] == "POST /locks/acquire"
        assert d["verdict"] == "pass"
        assert "duration_seconds" in d
        assert "backend_used" in d

    def test_unknown_interface_for_empty_interfaces_tested(self) -> None:
        verdict = ScenarioVerdict(
            scenario_id="x",
            scenario_name="X",
            status="pass",
            steps=[],
            interfaces_tested=[],
            category="test",
        )
        report = _make_report(verdicts=[verdict])
        metrics = report.to_metrics()
        assert metrics[0].interface == "unknown"
