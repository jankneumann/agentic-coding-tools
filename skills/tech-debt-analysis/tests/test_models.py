"""Tests for the tech-debt-analysis data models."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from models import (
    AnalyzerResult,
    TechDebtFinding,
    TechDebtReport,
    severity_rank,
)


class TestSeverityRank:
    def test_known_severities(self) -> None:
        assert severity_rank("info") == 0
        assert severity_rank("low") == 1
        assert severity_rank("medium") == 2
        assert severity_rank("high") == 3
        assert severity_rank("critical") == 4

    def test_unknown_severity(self) -> None:
        assert severity_rank("unknown") == 0

    def test_case_insensitive(self) -> None:
        assert severity_rank("HIGH") == 3
        assert severity_rank("Medium") == 2


class TestTechDebtFinding:
    def test_to_dict(self) -> None:
        f = TechDebtFinding(
            id="td-test-1",
            analyzer="complexity",
            severity="high",
            category="long-method",
            title="Long method: foo()",
            file_path="src/foo.py",
            line=10,
            metric_name="function_lines",
            metric_value=120,
            threshold=50,
        )
        d = f.to_dict()
        assert d["id"] == "td-test-1"
        assert d["severity"] == "high"
        assert d["metric_value"] == 120

    def test_defaults(self) -> None:
        f = TechDebtFinding(
            id="td-min",
            analyzer="test",
            severity="low",
            category="large-file",
            title="Test",
        )
        assert f.detail == ""
        assert f.line is None
        assert f.metric_value == 0.0


class TestAnalyzerResult:
    def test_to_dict(self) -> None:
        finding = TechDebtFinding(
            id="f1",
            analyzer="test",
            severity="medium",
            category="long-method",
            title="Test finding",
        )
        ar = AnalyzerResult(
            analyzer="test",
            status="ok",
            findings=[finding],
            duration_ms=42,
        )
        d = ar.to_dict()
        assert d["analyzer"] == "test"
        assert d["status"] == "ok"
        assert len(d["findings"]) == 1
        assert d["duration_ms"] == 42


class TestTechDebtReport:
    def _make_report(self) -> TechDebtReport:
        findings = [
            TechDebtFinding(
                id="f1", analyzer="complexity", severity="high",
                category="long-method", title="Long method",
                file_path="a.py",
            ),
            TechDebtFinding(
                id="f2", analyzer="complexity", severity="medium",
                category="complex-function", title="Complex function",
                file_path="a.py",
            ),
            TechDebtFinding(
                id="f3", analyzer="duplication", severity="low",
                category="duplicate-code", title="Duplicate code",
                file_path="b.py",
            ),
        ]
        return TechDebtReport(
            timestamp="2025-01-01T00:00:00Z",
            analyzers_used=["complexity", "duplication"],
            severity_filter="low",
            findings=findings,
        )

    def test_summary_by_severity(self) -> None:
        report = self._make_report()
        s = report.summary_by_severity()
        assert s["high"] == 1
        assert s["medium"] == 1
        assert s["low"] == 1

    def test_summary_by_category(self) -> None:
        report = self._make_report()
        s = report.summary_by_category()
        assert s["long-method"] == 1
        assert s["complex-function"] == 1
        assert s["duplicate-code"] == 1

    def test_hotspot_files(self) -> None:
        report = self._make_report()
        hotspots = report.hotspot_files()
        assert hotspots[0] == ("a.py", 2)  # a.py has 2 findings

    def test_to_dict_has_summary(self) -> None:
        report = self._make_report()
        d = report.to_dict()
        assert "summary" in d
        assert d["summary"]["total"] == 3
        assert len(d["summary"]["hotspot_files"]) > 0
