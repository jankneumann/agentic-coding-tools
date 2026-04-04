"""Tests for the tech-debt aggregator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aggregate import aggregate
from models import AnalyzerResult, TechDebtFinding


def _finding(
    id: str,
    severity: str = "medium",
    category: str = "long-method",
    file_path: str = "test.py",
    **kwargs,
) -> TechDebtFinding:
    return TechDebtFinding(
        id=id,
        analyzer="test",
        severity=severity,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        title=f"Test: {id}",
        file_path=file_path,
        **kwargs,
    )


class TestAggregate:
    def test_merges_findings(self) -> None:
        r1 = AnalyzerResult(
            analyzer="a1", status="ok",
            findings=[_finding("f1")],
        )
        r2 = AnalyzerResult(
            analyzer="a2", status="ok",
            findings=[_finding("f2")],
        )
        report = aggregate([r1, r2], timestamp="2025-01-01T00:00:00Z")
        assert len(report.findings) == 2
        assert set(report.analyzers_used) == {"a1", "a2"}

    def test_severity_filter(self) -> None:
        r = AnalyzerResult(
            analyzer="test", status="ok",
            findings=[
                _finding("f1", severity="high"),
                _finding("f2", severity="low"),
                _finding("f3", severity="medium"),
            ],
        )
        report = aggregate([r], severity_filter="medium")
        assert len(report.findings) == 2
        assert report.filtered_out_count == 1

    def test_sorted_by_severity(self) -> None:
        r = AnalyzerResult(
            analyzer="test", status="ok",
            findings=[
                _finding("low", severity="low"),
                _finding("high", severity="high"),
                _finding("med", severity="medium"),
            ],
        )
        report = aggregate([r])
        severities = [f.severity for f in report.findings]
        assert severities == ["high", "medium", "low"]

    def test_recommendations_generated(self) -> None:
        findings = [
            _finding(f"long-{i}", severity="high", category="long-method")
            for i in range(5)
        ]
        findings += [
            _finding(f"complex-{i}", severity="high", category="complex-function")
            for i in range(5)
        ]
        r = AnalyzerResult(analyzer="test", status="ok", findings=findings)
        report = aggregate([r])
        assert len(report.recommendations) > 0

    def test_empty_results(self) -> None:
        r = AnalyzerResult(analyzer="test", status="ok", findings=[])
        report = aggregate([r])
        assert len(report.findings) == 0
        assert report.filtered_out_count == 0
