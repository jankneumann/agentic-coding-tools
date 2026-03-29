"""Tests for render_report: markdown, JSON, and file-writing behaviour."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from models import BugScrubReport, Finding
from render_report import render_json, render_markdown, write_report

# ---------------------------------------------------------------------------
# Fixtures — reusable sample data
# ---------------------------------------------------------------------------


def _make_finding(
    id: str,
    severity: str,
    *,
    source: str = "pytest",
    category: str = "test-failure",
    title: str = "sample finding",
    detail: str = "",
    file_path: str = "",
    line: int | None = None,
    age_days: int | None = None,
) -> Finding:
    return Finding(
        id=id,
        source=source,
        severity=severity,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        title=title,
        detail=detail,
        file_path=file_path,
        line=line,
        age_days=age_days,
    )


@pytest.fixture()
def mixed_report() -> BugScrubReport:
    """Report with findings at every severity level."""
    return BugScrubReport(
        timestamp="2026-02-21T10:00:00Z",
        sources_used=["pytest", "ruff", "mypy"],
        severity_filter="info",
        findings=[
            _make_finding(
                "f-1",
                "critical",
                source="pytest",
                title="Segfault in parser",
                detail="Core dump on malformed input",
                file_path="src/parser.py",
                line=42,
                age_days=3,
            ),
            _make_finding(
                "f-2",
                "high",
                source="mypy",
                title="Type mismatch in handler",
                file_path="src/handler.py",
                line=100,
            ),
            _make_finding(
                "f-3",
                "medium",
                source="ruff",
                title="Unused import",
                file_path="src/utils.py",
                line=7,
            ),
            _make_finding(
                "f-4",
                "medium",
                source="ruff",
                title="Line too long",
                file_path="src/models.py",
                line=55,
            ),
            _make_finding(
                "f-5",
                "low",
                source="ruff",
                title="Trailing whitespace",
            ),
            _make_finding(
                "f-6",
                "info",
                source="ruff",
                title="Missing docstring",
            ),
            _make_finding(
                "f-7",
                "info",
                source="ruff",
                title="Consider using pathlib",
            ),
        ],
        staleness_warnings=["ruff config older than 30 days"],
        recommendations=["Upgrade ruff to v0.9"],
    )


@pytest.fixture()
def empty_report() -> BugScrubReport:
    """Report with zero findings and no warnings."""
    return BugScrubReport(
        timestamp="2026-02-21T10:00:00Z",
        sources_used=["pytest"],
        severity_filter="info",
    )


@pytest.fixture()
def empty_report_with_warnings() -> BugScrubReport:
    """Report with zero findings but staleness warnings present."""
    return BugScrubReport(
        timestamp="2026-02-21T10:00:00Z",
        sources_used=["pytest"],
        severity_filter="medium",
        staleness_warnings=["pytest cache is stale"],
    )


# ---------------------------------------------------------------------------
# 1. Markdown output contains expected sections
# ---------------------------------------------------------------------------


class TestMarkdownSections:
    def test_header_present(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "# Bug Scrub Report" in md
        assert "**Timestamp**: 2026-02-21T10:00:00Z" in md
        assert "**Sources**: pytest, ruff, mypy" in md
        assert "**Severity filter**: info" in md
        assert "**Total findings**: 7" in md

    def test_summary_tables_present(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Summary" in md
        assert "### By Severity" in md
        assert "| Severity | Count |" in md
        assert "### By Source" in md
        assert "| Source | Count |" in md

    def test_critical_high_section(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Critical / High Findings" in md

    def test_medium_section(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Medium Findings" in md

    def test_low_info_section(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Low / Info Findings" in md

    def test_staleness_section(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Staleness Warnings" in md
        assert "ruff config older than 30 days" in md

    def test_recommendations_section(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "## Recommendations" in md
        assert "1. Upgrade ruff to v0.9" in md


# ---------------------------------------------------------------------------
# 2. JSON serialization round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_json_is_valid(self, mixed_report: BugScrubReport) -> None:
        raw = render_json(mixed_report)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_json_fields_present(self, mixed_report: BugScrubReport) -> None:
        parsed = json.loads(render_json(mixed_report))
        assert parsed["timestamp"] == "2026-02-21T10:00:00Z"
        assert parsed["sources_used"] == ["pytest", "ruff", "mypy"]
        assert parsed["severity_filter"] == "info"
        assert len(parsed["findings"]) == 7

    def test_json_summary_matches(self, mixed_report: BugScrubReport) -> None:
        parsed = json.loads(render_json(mixed_report))
        summary = parsed["summary"]
        assert summary["total"] == 7
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_severity"]["high"] == 1
        assert summary["by_severity"]["medium"] == 2
        assert summary["by_severity"]["low"] == 1
        assert summary["by_severity"]["info"] == 2

    def test_json_finding_detail(self, mixed_report: BugScrubReport) -> None:
        parsed = json.loads(render_json(mixed_report))
        critical = [f for f in parsed["findings"] if f["severity"] == "critical"]
        assert len(critical) == 1
        assert critical[0]["title"] == "Segfault in parser"
        assert critical[0]["file_path"] == "src/parser.py"
        assert critical[0]["line"] == 42
        assert critical[0]["age_days"] == 3

    def test_empty_report_json(self, empty_report: BugScrubReport) -> None:
        parsed = json.loads(render_json(empty_report))
        assert parsed["findings"] == []
        assert parsed["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# 3. Severity filtering in markdown output
# ---------------------------------------------------------------------------


class TestSeverityFiltering:
    def test_critical_high_get_full_detail(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        # Critical finding renders with full detail block
        assert "### [CRITICAL] Segfault in parser" in md
        assert "- **Source**: pytest" in md
        assert "- **Location**: src/parser.py:42" in md
        assert "- **Age**: 3 days" in md
        assert "- **Detail**: Core dump on malformed input" in md
        # High finding also gets full detail
        assert "### [HIGH] Type mismatch in handler" in md
        assert "- **Location**: src/handler.py:100" in md

    def test_medium_condensed_table(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        # Medium findings appear in table format, not full detail blocks
        assert "| ruff | src/utils.py:7 | Unused import |" in md
        assert "| ruff | src/models.py:55 | Line too long |" in md
        # Medium titles should NOT appear as ### headings
        assert "### [MEDIUM]" not in md

    def test_low_info_counts_only(self, mixed_report: BugScrubReport) -> None:
        md = render_markdown(mixed_report)
        assert "- **Low**: 1 findings" in md
        assert "- **Info**: 2 findings" in md
        assert "_(See JSON report for full details)_" in md
        # Individual low/info titles should not appear in markdown
        assert "Trailing whitespace" not in md
        assert "Missing docstring" not in md
        assert "Consider using pathlib" not in md


# ---------------------------------------------------------------------------
# 4. Empty report — "Clean bill of health"
# ---------------------------------------------------------------------------


class TestEmptyReport:
    def test_clean_bill_of_health(self, empty_report: BugScrubReport) -> None:
        md = render_markdown(empty_report)
        assert "Clean bill of health" in md
        # Should not have findings sections
        assert "## Critical / High Findings" not in md
        assert "## Medium Findings" not in md
        assert "## Low / Info Findings" not in md

    def test_no_findings_with_warnings(
        self, empty_report_with_warnings: BugScrubReport
    ) -> None:
        md = render_markdown(empty_report_with_warnings)
        assert "No findings at or above the severity threshold." in md
        assert "Clean bill of health" not in md
        assert "## Staleness Warnings" in md


# ---------------------------------------------------------------------------
# 5. write_report creates files in correct directory
# ---------------------------------------------------------------------------


class TestWriteReport:
    def test_write_creates_md_and_json(
        self, tmp_path: Path, mixed_report: BugScrubReport
    ) -> None:
        written = write_report(mixed_report, str(tmp_path), fmt="both")
        assert len(written) == 2
        md_path = tmp_path / "bug-scrub-report.md"
        json_path = tmp_path / "bug-scrub-report.json"
        assert md_path.exists()
        assert json_path.exists()
        assert str(md_path) in written
        assert str(json_path) in written

    def test_md_file_content(
        self, tmp_path: Path, mixed_report: BugScrubReport
    ) -> None:
        write_report(mixed_report, str(tmp_path), fmt="md")
        md_path = tmp_path / "bug-scrub-report.md"
        content = md_path.read_text()
        assert "# Bug Scrub Report" in content

    def test_json_file_content(
        self, tmp_path: Path, mixed_report: BugScrubReport
    ) -> None:
        write_report(mixed_report, str(tmp_path), fmt="json")
        json_path = tmp_path / "bug-scrub-report.json"
        parsed = json.loads(json_path.read_text())
        assert parsed["timestamp"] == "2026-02-21T10:00:00Z"

    def test_creates_output_directory(
        self, tmp_path: Path, empty_report: BugScrubReport
    ) -> None:
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()
        write_report(empty_report, str(nested), fmt="both")
        assert nested.exists()
        assert (nested / "bug-scrub-report.md").exists()
        assert (nested / "bug-scrub-report.json").exists()


# ---------------------------------------------------------------------------
# 6. Format options (md-only, json-only, both)
# ---------------------------------------------------------------------------


class TestFormatOptions:
    def test_md_only(self, tmp_path: Path, mixed_report: BugScrubReport) -> None:
        written = write_report(mixed_report, str(tmp_path), fmt="md")
        assert len(written) == 1
        assert written[0].endswith("bug-scrub-report.md")
        assert not (tmp_path / "bug-scrub-report.json").exists()

    def test_json_only(self, tmp_path: Path, mixed_report: BugScrubReport) -> None:
        written = write_report(mixed_report, str(tmp_path), fmt="json")
        assert len(written) == 1
        assert written[0].endswith("bug-scrub-report.json")
        assert not (tmp_path / "bug-scrub-report.md").exists()

    def test_both(self, tmp_path: Path, mixed_report: BugScrubReport) -> None:
        written = write_report(mixed_report, str(tmp_path), fmt="both")
        assert len(written) == 2
        extensions = {Path(p).suffix for p in written}
        assert extensions == {".md", ".json"}

    def test_default_is_both(
        self, tmp_path: Path, mixed_report: BugScrubReport
    ) -> None:
        written = write_report(mixed_report, str(tmp_path))
        assert len(written) == 2
        assert (tmp_path / "bug-scrub-report.md").exists()
        assert (tmp_path / "bug-scrub-report.json").exists()
