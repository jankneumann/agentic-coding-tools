"""Tests for the tech-debt report renderer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from models import AnalyzerResult, TechDebtFinding, TechDebtReport
from render_report import render_json, render_markdown, write_report


def _make_report() -> TechDebtReport:
    findings = [
        TechDebtFinding(
            id="f1", analyzer="complexity", severity="high",
            category="long-method", title="Long method: foo()",
            file_path="src/foo.py", line=10,
            metric_name="function_lines", metric_value=120,
            threshold=50, smell="Long Method",
            recommendation="Extract Method",
        ),
        TechDebtFinding(
            id="f2", analyzer="complexity", severity="medium",
            category="complex-function", title="Complex: bar()",
            file_path="src/bar.py", line=5,
            metric_name="cyclomatic_complexity", metric_value=15,
            threshold=10,
        ),
        TechDebtFinding(
            id="f3", analyzer="duplication", severity="low",
            category="duplicate-code", title="Duplicate block",
            file_path="src/dup.py",
        ),
    ]
    return TechDebtReport(
        timestamp="2025-01-01T00:00:00Z",
        analyzers_used=["complexity", "duplication"],
        severity_filter="low",
        findings=findings,
        analyzer_results=[
            AnalyzerResult(
                analyzer="complexity", status="ok",
                findings=findings[:2], duration_ms=100,
            ),
            AnalyzerResult(
                analyzer="duplication", status="ok",
                findings=findings[2:], duration_ms=50,
            ),
        ],
        recommendations=["Fix long methods first"],
    )


class TestRenderMarkdown:
    def test_contains_header(self) -> None:
        md = render_markdown(_make_report())
        assert "# Tech Debt Analysis Report" in md

    def test_contains_severity_table(self) -> None:
        md = render_markdown(_make_report())
        assert "| high | 1 |" in md

    def test_contains_category_table(self) -> None:
        md = render_markdown(_make_report())
        assert "long-method" in md

    def test_contains_hotspot_files(self) -> None:
        md = render_markdown(_make_report())
        assert "Hotspot" in md

    def test_contains_high_finding_detail(self) -> None:
        md = render_markdown(_make_report())
        assert "[HIGH]" in md
        assert "foo()" in md

    def test_contains_recommendations(self) -> None:
        md = render_markdown(_make_report())
        assert "Fix long methods first" in md

    def test_empty_report(self) -> None:
        report = TechDebtReport(
            timestamp="2025-01-01T00:00:00Z",
            analyzers_used=["test"],
            severity_filter="low",
        )
        md = render_markdown(report)
        assert "good shape" in md

    def test_contains_analyzer_performance(self) -> None:
        md = render_markdown(_make_report())
        assert "Analyzer Performance" in md
        assert "100ms" in md


class TestRenderJson:
    def test_valid_json(self) -> None:
        raw = render_json(_make_report())
        data = json.loads(raw)
        assert data["timestamp"] == "2025-01-01T00:00:00Z"
        assert data["summary"]["total"] == 3

    def test_findings_in_json(self) -> None:
        raw = render_json(_make_report())
        data = json.loads(raw)
        assert len(data["findings"]) == 3
        assert data["findings"][0]["id"] == "f1"


class TestWriteReport:
    def test_writes_both_formats(self, tmp_path: Path) -> None:
        report = _make_report()
        written = write_report(report, str(tmp_path), "both")
        assert len(written) == 2
        assert any("tech-debt-report.md" in p for p in written)
        assert any("tech-debt-report.json" in p for p in written)

    def test_writes_md_only(self, tmp_path: Path) -> None:
        report = _make_report()
        written = write_report(report, str(tmp_path), "md")
        assert len(written) == 1
        assert "tech-debt-report.md" in written[0]

    def test_writes_json_only(self, tmp_path: Path) -> None:
        report = _make_report()
        written = write_report(report, str(tmp_path), "json")
        assert len(written) == 1
        assert "tech-debt-report.json" in written[0]

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "output"
        write_report(_make_report(), str(out), "both")
        assert out.exists()
