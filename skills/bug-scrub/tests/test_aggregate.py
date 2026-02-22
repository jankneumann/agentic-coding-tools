"""Tests for the bug-scrub aggregation module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aggregate import aggregate, _generate_recommendations
from models import Finding, FindingOrigin, SourceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(
    id: str = "f1",
    source: str = "test-runner",
    severity: str = "medium",
    category: str = "lint",
    title: str = "dummy",
    age_days: int | None = None,
    file_path: str = "",
    line: int | None = None,
    origin: FindingOrigin | None = None,
) -> Finding:
    return Finding(
        id=id,
        source=source,
        severity=severity,
        category=category,
        title=title,
        age_days=age_days,
        file_path=file_path,
        line=line,
        origin=origin,
    )


def _source(
    source: str = "src",
    findings: list[Finding] | None = None,
    messages: list[str] | None = None,
) -> SourceResult:
    return SourceResult(
        source=source,
        status="ok",
        findings=findings or [],
        messages=messages or [],
    )


# ---------------------------------------------------------------------------
# 1. Severity sorting (critical first, then high, medium, low, info)
# ---------------------------------------------------------------------------

class TestSeveritySorting:
    def test_findings_sorted_critical_first(self):
        sr = _source(findings=[
            _finding(id="low1", severity="low"),
            _finding(id="crit1", severity="critical"),
            _finding(id="med1", severity="medium"),
            _finding(id="high1", severity="high"),
            _finding(id="info1", severity="info"),
        ])
        report = aggregate([sr], severity_filter="info")
        severities = [f.severity for f in report.findings]
        assert severities == ["critical", "high", "medium", "low", "info"]

    def test_multiple_critical_before_high(self):
        sr = _source(findings=[
            _finding(id="h1", severity="high"),
            _finding(id="c1", severity="critical"),
            _finding(id="c2", severity="critical"),
            _finding(id="h2", severity="high"),
        ])
        report = aggregate([sr])
        severities = [f.severity for f in report.findings]
        assert severities == ["critical", "critical", "high", "high"]


# ---------------------------------------------------------------------------
# 2. Age sorting within same severity (oldest first)
# ---------------------------------------------------------------------------

class TestAgeSorting:
    def test_oldest_first_within_same_severity(self):
        sr = _source(findings=[
            _finding(id="new", severity="high", age_days=1),
            _finding(id="old", severity="high", age_days=30),
            _finding(id="mid", severity="high", age_days=10),
        ])
        report = aggregate([sr])
        ages = [f.age_days for f in report.findings]
        assert ages == [30, 10, 1]

    def test_age_sort_stable_across_severities(self):
        sr = _source(findings=[
            _finding(id="c_new", severity="critical", age_days=2),
            _finding(id="c_old", severity="critical", age_days=50),
            _finding(id="h_new", severity="high", age_days=5),
            _finding(id="h_old", severity="high", age_days=40),
        ])
        report = aggregate([sr])
        ids = [f.id for f in report.findings]
        assert ids == ["c_old", "c_new", "h_old", "h_new"]

    def test_none_age_treated_as_zero(self):
        sr = _source(findings=[
            _finding(id="no_age", severity="medium", age_days=None),
            _finding(id="has_age", severity="medium", age_days=10),
        ])
        report = aggregate([sr])
        ids = [f.id for f in report.findings]
        assert ids == ["has_age", "no_age"]


# ---------------------------------------------------------------------------
# 3. Severity filtering (only findings at or above threshold)
# ---------------------------------------------------------------------------

class TestSeverityFiltering:
    def test_filter_at_medium_excludes_low_and_info(self):
        sr = _source(findings=[
            _finding(id="crit", severity="critical"),
            _finding(id="high", severity="high"),
            _finding(id="med", severity="medium"),
            _finding(id="low", severity="low"),
            _finding(id="info", severity="info"),
        ])
        report = aggregate([sr], severity_filter="medium")
        ids = {f.id for f in report.findings}
        assert ids == {"crit", "high", "med"}

    def test_filter_at_critical_only_critical(self):
        sr = _source(findings=[
            _finding(id="crit", severity="critical"),
            _finding(id="high", severity="high"),
            _finding(id="med", severity="medium"),
        ])
        report = aggregate([sr], severity_filter="critical")
        assert len(report.findings) == 1
        assert report.findings[0].id == "crit"

    def test_filter_at_info_includes_everything(self):
        sr = _source(findings=[
            _finding(id="crit", severity="critical"),
            _finding(id="info", severity="info"),
        ])
        report = aggregate([sr], severity_filter="info")
        assert len(report.findings) == 2

    def test_filter_at_low_is_default_includes_all_except_info(self):
        sr = _source(findings=[
            _finding(id="crit", severity="critical"),
            _finding(id="low", severity="low"),
            _finding(id="info", severity="info"),
        ])
        report = aggregate([sr])  # default severity_filter="low"
        ids = {f.id for f in report.findings}
        assert ids == {"crit", "low"}

    def test_filter_at_high_excludes_medium_low_info(self):
        sr = _source(findings=[
            _finding(id="crit", severity="critical"),
            _finding(id="high", severity="high"),
            _finding(id="med", severity="medium"),
            _finding(id="low", severity="low"),
            _finding(id="info", severity="info"),
        ])
        report = aggregate([sr], severity_filter="high")
        ids = {f.id for f in report.findings}
        assert ids == {"crit", "high"}


# ---------------------------------------------------------------------------
# 4. Summary count generation (by severity and by source)
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    def test_summary_by_severity(self):
        sr = _source(findings=[
            _finding(id="c1", severity="critical"),
            _finding(id="c2", severity="critical"),
            _finding(id="h1", severity="high"),
            _finding(id="m1", severity="medium"),
        ])
        report = aggregate([sr])
        by_sev = report.summary_by_severity()
        assert by_sev == {"critical": 2, "high": 1, "medium": 1}

    def test_summary_by_source(self):
        findings = [
            _finding(id="a1", source="ruff"),
            _finding(id="a2", source="ruff"),
            _finding(id="b1", source="pytest"),
            _finding(id="c1", source="mypy"),
            _finding(id="c2", source="mypy"),
            _finding(id="c3", source="mypy"),
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        by_src = report.summary_by_source()
        assert by_src == {"ruff": 2, "pytest": 1, "mypy": 3}

    def test_summary_from_multiple_source_results(self):
        sr1 = _source(source="ruff", findings=[
            _finding(id="r1", source="ruff", severity="low"),
        ])
        sr2 = _source(source="pytest", findings=[
            _finding(id="p1", source="pytest", severity="high"),
            _finding(id="p2", source="pytest", severity="high"),
        ])
        report = aggregate([sr1, sr2])
        assert report.summary_by_source() == {"ruff": 1, "pytest": 2}
        assert report.summary_by_severity() == {"low": 1, "high": 2}

    def test_sources_used_lists_all_source_names(self):
        sr1 = _source(source="ruff")
        sr2 = _source(source="pytest")
        sr3 = _source(source="mypy")
        report = aggregate([sr1, sr2, sr3])
        assert report.sources_used == ["ruff", "pytest", "mypy"]


# ---------------------------------------------------------------------------
# 5. Recommendation logic
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_staleness_warnings_trigger_refresh(self):
        sr = _source(
            findings=[_finding(id="f1")],
            messages=["Architecture report is stale (45 days old)"],
        )
        report = aggregate([sr])
        assert any("Refresh stale reports" in r for r in report.recommendations)

    def test_more_than_five_test_failures_trigger_fix_tests(self):
        findings = [
            _finding(id=f"tf{i}", category="test-failure")
            for i in range(6)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert any("Fix failing tests" in r for r in report.recommendations)

    def test_exactly_five_test_failures_no_recommendation(self):
        findings = [
            _finding(id=f"tf{i}", category="test-failure")
            for i in range(5)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert not any("Fix failing tests" in r for r in report.recommendations)

    def test_more_than_ten_lint_findings_trigger_fix_scrub(self):
        findings = [
            _finding(id=f"l{i}", category="lint")
            for i in range(11)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert any("/fix-scrub --tier auto" in r for r in report.recommendations)

    def test_exactly_ten_lint_findings_no_recommendation(self):
        findings = [
            _finding(id=f"l{i}", category="lint")
            for i in range(10)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert not any("/fix-scrub --tier auto" in r for r in report.recommendations)

    def test_deferred_from_more_than_two_changes_trigger_consolidate(self):
        findings = [
            _finding(
                id=f"d{i}",
                category="deferred-issue",
                origin=FindingOrigin(
                    change_id=f"change-{i}",
                    artifact_path=f"path/{i}",
                ),
            )
            for i in range(3)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert any("Consolidate deferred" in r for r in report.recommendations)

    def test_deferred_from_two_changes_no_consolidate(self):
        findings = [
            _finding(
                id="d1",
                category="deferred-issue",
                origin=FindingOrigin(change_id="change-a", artifact_path="p/a"),
            ),
            _finding(
                id="d2",
                category="deferred-issue",
                origin=FindingOrigin(change_id="change-b", artifact_path="p/b"),
            ),
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert not any("Consolidate deferred" in r for r in report.recommendations)

    def test_deferred_same_change_no_consolidate(self):
        findings = [
            _finding(
                id=f"d{i}",
                category="deferred-issue",
                origin=FindingOrigin(change_id="same-change", artifact_path=f"p/{i}"),
            )
            for i in range(5)
        ]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert not any("Consolidate deferred" in r for r in report.recommendations)

    def test_more_than_twenty_findings_trigger_dry_run(self):
        findings = [_finding(id=f"f{i}") for i in range(21)]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert any("/fix-scrub --dry-run" in r for r in report.recommendations)

    def test_exactly_twenty_findings_no_dry_run(self):
        findings = [_finding(id=f"f{i}") for i in range(20)]
        sr = _source(findings=findings)
        report = aggregate([sr])
        assert not any("/fix-scrub --dry-run" in r for r in report.recommendations)

    def test_recommendations_capped_at_five(self):
        # Trigger all five recommendation paths simultaneously
        staleness_msg = "Architecture report is stale"
        test_failures = [
            _finding(id=f"tf{i}", category="test-failure") for i in range(6)
        ]
        lint_findings = [
            _finding(id=f"l{i}", category="lint") for i in range(11)
        ]
        deferred = [
            _finding(
                id=f"d{i}",
                category="deferred-issue",
                origin=FindingOrigin(change_id=f"change-{i}", artifact_path=f"p/{i}"),
            )
            for i in range(4)
        ]
        # Pad to exceed 20 total
        extra = [_finding(id=f"e{i}") for i in range(5)]
        all_findings = test_failures + lint_findings + deferred + extra
        sr = _source(findings=all_findings, messages=[staleness_msg])
        report = aggregate([sr])
        assert len(report.recommendations) <= 5

    def test_recommendation_priority_order(self):
        # All five recommendation types active; check ordering matches spec
        staleness_msg = "Report is stale"
        test_failures = [
            _finding(id=f"tf{i}", category="test-failure") for i in range(6)
        ]
        lint_findings = [
            _finding(id=f"l{i}", category="lint") for i in range(11)
        ]
        deferred = [
            _finding(
                id=f"d{i}",
                category="deferred-issue",
                origin=FindingOrigin(change_id=f"ch-{i}", artifact_path=f"p/{i}"),
            )
            for i in range(4)
        ]
        all_findings = test_failures + lint_findings + deferred
        sr = _source(findings=all_findings, messages=[staleness_msg])
        report = aggregate([sr])
        recs = report.recommendations
        # Per spec: staleness, test failures, lint, deferred, total count
        assert "Refresh stale reports" in recs[0]
        assert "Fix failing tests" in recs[1]
        assert "/fix-scrub --tier auto" in recs[2]
        assert "Consolidate deferred" in recs[3]


# ---------------------------------------------------------------------------
# 6. Empty report (no findings)
# ---------------------------------------------------------------------------

class TestEmptyReport:
    def test_empty_source_results(self):
        report = aggregate([])
        assert report.findings == []
        assert report.recommendations == []
        assert report.staleness_warnings == []
        assert report.sources_used == []

    def test_source_with_no_findings(self):
        sr = _source(source="ruff", findings=[])
        report = aggregate([sr])
        assert report.findings == []
        assert report.sources_used == ["ruff"]
        assert report.summary_by_severity() == {}
        assert report.summary_by_source() == {}

    def test_empty_report_to_dict(self):
        report = aggregate([], timestamp="2026-02-21T00:00:00Z")
        d = report.to_dict()
        assert d["findings"] == []
        assert d["summary"]["total"] == 0
        assert d["summary"]["by_severity"] == {}
        assert d["summary"]["by_source"] == {}
        assert d["timestamp"] == "2026-02-21T00:00:00Z"


# ---------------------------------------------------------------------------
# 7. Staleness warnings collected from source messages
# ---------------------------------------------------------------------------

class TestStalenessWarnings:
    def test_stale_keyword_detected(self):
        sr = _source(
            findings=[_finding(id="f1")],
            messages=["Architecture report is stale (45 days old)"],
        )
        report = aggregate([sr])
        assert len(report.staleness_warnings) == 1
        assert "stale" in report.staleness_warnings[0].lower()

    def test_staleness_keyword_detected(self):
        sr = _source(
            findings=[_finding(id="f1")],
            messages=["Staleness detected in security review"],
        )
        report = aggregate([sr])
        assert len(report.staleness_warnings) == 1
        assert "staleness" in report.staleness_warnings[0].lower()

    def test_no_staleness_in_normal_messages(self):
        sr = _source(
            findings=[_finding(id="f1")],
            messages=["All checks passed", "Completed in 200ms"],
        )
        report = aggregate([sr])
        assert report.staleness_warnings == []

    def test_multiple_stale_messages_from_multiple_sources(self):
        sr1 = _source(
            source="arch",
            findings=[],
            messages=["Architecture is stale"],
        )
        sr2 = _source(
            source="security",
            findings=[],
            messages=["Security review stale since January"],
        )
        sr3 = _source(
            source="lint",
            findings=[],
            messages=["Everything is fine"],
        )
        report = aggregate([sr1, sr2, sr3])
        assert len(report.staleness_warnings) == 2

    def test_case_insensitive_staleness_detection(self):
        sr = _source(
            findings=[],
            messages=["STALE data found in report"],
        )
        report = aggregate([sr])
        assert len(report.staleness_warnings) == 1
