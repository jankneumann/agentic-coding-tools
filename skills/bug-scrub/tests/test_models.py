"""Tests for bug-scrub shared data models."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from models import (
    BugScrubReport,
    Finding,
    FindingOrigin,
    SourceResult,
    severity_rank,
)


# ---------------------------------------------------------------------------
# FindingOrigin
# ---------------------------------------------------------------------------


class TestFindingOrigin:
    def test_creation_all_fields(self) -> None:
        origin = FindingOrigin(
            change_id="chg-42",
            artifact_path="openspec/changes/chg-42/proposal.md",
            task_number="T3",
            line_in_artifact=17,
        )
        assert origin.change_id == "chg-42"
        assert origin.artifact_path == "openspec/changes/chg-42/proposal.md"
        assert origin.task_number == "T3"
        assert origin.line_in_artifact == 17

    def test_creation_defaults(self) -> None:
        origin = FindingOrigin(
            change_id="chg-1",
            artifact_path="specs/req.md",
        )
        assert origin.task_number is None
        assert origin.line_in_artifact is None

    def test_to_dict(self) -> None:
        origin = FindingOrigin(
            change_id="chg-42",
            artifact_path="proposal.md",
            task_number="T1",
            line_in_artifact=5,
        )
        d = origin.to_dict()
        assert d == {
            "change_id": "chg-42",
            "artifact_path": "proposal.md",
            "task_number": "T1",
            "line_in_artifact": 5,
        }

    def test_to_dict_with_none_optionals(self) -> None:
        origin = FindingOrigin(change_id="c", artifact_path="a.md")
        d = origin.to_dict()
        assert d["task_number"] is None
        assert d["line_in_artifact"] is None


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class TestFinding:
    def _make_finding(self, **overrides: object) -> Finding:
        defaults = {
            "id": "f-1",
            "source": "pytest",
            "severity": "high",
            "category": "test-failure",
            "title": "test_foo failed",
            "detail": "AssertionError: 1 != 2",
            "file_path": "tests/test_foo.py",
            "line": 42,
            "age_days": 3,
            "origin": None,
        }
        defaults.update(overrides)
        return Finding(**defaults)  # type: ignore[arg-type]

    def test_creation_all_fields(self) -> None:
        origin = FindingOrigin(change_id="c1", artifact_path="p.md")
        f = self._make_finding(origin=origin)
        assert f.id == "f-1"
        assert f.source == "pytest"
        assert f.severity == "high"
        assert f.category == "test-failure"
        assert f.title == "test_foo failed"
        assert f.detail == "AssertionError: 1 != 2"
        assert f.file_path == "tests/test_foo.py"
        assert f.line == 42
        assert f.age_days == 3
        assert f.origin is origin

    def test_creation_defaults(self) -> None:
        f = Finding(
            id="f-2",
            source="ruff",
            severity="low",
            category="lint",
            title="unused import",
        )
        assert f.detail == ""
        assert f.file_path == ""
        assert f.line is None
        assert f.age_days is None
        assert f.origin is None

    def test_to_dict_without_origin(self) -> None:
        f = self._make_finding()
        d = f.to_dict()
        assert d == {
            "id": "f-1",
            "source": "pytest",
            "severity": "high",
            "category": "test-failure",
            "title": "test_foo failed",
            "detail": "AssertionError: 1 != 2",
            "file_path": "tests/test_foo.py",
            "line": 42,
            "age_days": 3,
            "origin": None,
        }

    def test_to_dict_with_origin(self) -> None:
        origin = FindingOrigin(
            change_id="chg-7",
            artifact_path="specs/req.md",
            task_number="T2",
            line_in_artifact=10,
        )
        f = self._make_finding(origin=origin)
        d = f.to_dict()
        assert d["origin"] == {
            "change_id": "chg-7",
            "artifact_path": "specs/req.md",
            "task_number": "T2",
            "line_in_artifact": 10,
        }

    def test_to_dict_origin_none_is_explicit(self) -> None:
        """origin key must be present and explicitly None, not omitted."""
        f = self._make_finding()
        d = f.to_dict()
        assert "origin" in d
        assert d["origin"] is None


# ---------------------------------------------------------------------------
# SourceResult
# ---------------------------------------------------------------------------


class TestSourceResult:
    def test_creation_all_fields(self) -> None:
        finding = Finding(
            id="f-1",
            source="ruff",
            severity="low",
            category="lint",
            title="unused import",
        )
        sr = SourceResult(
            source="ruff",
            status="ok",
            findings=[finding],
            duration_ms=123,
            messages=["Checked 10 files"],
        )
        assert sr.source == "ruff"
        assert sr.status == "ok"
        assert sr.findings == [finding]
        assert sr.duration_ms == 123
        assert sr.messages == ["Checked 10 files"]

    def test_creation_defaults(self) -> None:
        sr = SourceResult(source="mypy", status="skipped")
        assert sr.findings == []
        assert sr.duration_ms == 0
        assert sr.messages == []

    def test_to_dict(self) -> None:
        finding = Finding(
            id="f-1",
            source="ruff",
            severity="medium",
            category="lint",
            title="E501 line too long",
        )
        sr = SourceResult(
            source="ruff",
            status="ok",
            findings=[finding],
            duration_ms=50,
            messages=["done"],
        )
        d = sr.to_dict()
        assert d["source"] == "ruff"
        assert d["status"] == "ok"
        assert d["duration_ms"] == 50
        assert d["messages"] == ["done"]
        assert len(d["findings"]) == 1
        assert d["findings"][0]["id"] == "f-1"

    def test_to_dict_empty_findings(self) -> None:
        sr = SourceResult(source="mypy", status="error", messages=["crash"])
        d = sr.to_dict()
        assert d["findings"] == []


# ---------------------------------------------------------------------------
# BugScrubReport
# ---------------------------------------------------------------------------


class TestBugScrubReport:
    def _make_report(self) -> BugScrubReport:
        findings = [
            Finding(
                id="f-1",
                source="pytest",
                severity="critical",
                category="test-failure",
                title="crash in test_a",
            ),
            Finding(
                id="f-2",
                source="pytest",
                severity="high",
                category="test-failure",
                title="assertion in test_b",
            ),
            Finding(
                id="f-3",
                source="ruff",
                severity="low",
                category="lint",
                title="unused variable",
            ),
            Finding(
                id="f-4",
                source="ruff",
                severity="critical",
                category="lint",
                title="syntax error",
            ),
        ]
        sr_pytest = SourceResult(
            source="pytest", status="ok", findings=findings[:2], duration_ms=400
        )
        sr_ruff = SourceResult(
            source="ruff", status="ok", findings=findings[2:], duration_ms=60
        )
        return BugScrubReport(
            timestamp="2026-02-21T12:00:00Z",
            sources_used=["pytest", "ruff"],
            severity_filter="low",
            findings=findings,
            staleness_warnings=["openspec cache is 3 days old"],
            recommendations=["Fix critical findings first"],
            source_results=[sr_pytest, sr_ruff],
        )

    def test_creation(self) -> None:
        report = self._make_report()
        assert report.timestamp == "2026-02-21T12:00:00Z"
        assert report.sources_used == ["pytest", "ruff"]
        assert report.severity_filter == "low"
        assert len(report.findings) == 4
        assert report.staleness_warnings == ["openspec cache is 3 days old"]
        assert report.recommendations == ["Fix critical findings first"]
        assert len(report.source_results) == 2

    def test_creation_defaults(self) -> None:
        report = BugScrubReport(
            timestamp="t",
            sources_used=[],
            severity_filter="info",
        )
        assert report.findings == []
        assert report.staleness_warnings == []
        assert report.recommendations == []
        assert report.source_results == []

    def test_summary_by_severity(self) -> None:
        report = self._make_report()
        summary = report.summary_by_severity()
        assert summary == {"critical": 2, "high": 1, "low": 1}

    def test_summary_by_severity_empty(self) -> None:
        report = BugScrubReport(
            timestamp="t", sources_used=[], severity_filter="info"
        )
        assert report.summary_by_severity() == {}

    def test_summary_by_source(self) -> None:
        report = self._make_report()
        summary = report.summary_by_source()
        assert summary == {"pytest": 2, "ruff": 2}

    def test_summary_by_source_empty(self) -> None:
        report = BugScrubReport(
            timestamp="t", sources_used=[], severity_filter="info"
        )
        assert report.summary_by_source() == {}

    def test_to_dict(self) -> None:
        report = self._make_report()
        d = report.to_dict()
        assert d["timestamp"] == "2026-02-21T12:00:00Z"
        assert d["sources_used"] == ["pytest", "ruff"]
        assert d["severity_filter"] == "low"
        assert len(d["findings"]) == 4
        assert d["staleness_warnings"] == ["openspec cache is 3 days old"]
        assert d["recommendations"] == ["Fix critical findings first"]
        assert len(d["source_results"]) == 2
        # Summary block
        assert d["summary"]["total"] == 4
        assert d["summary"]["by_severity"] == {"critical": 2, "high": 1, "low": 1}
        assert d["summary"]["by_source"] == {"pytest": 2, "ruff": 2}

    def test_to_dict_serializes_nested_findings(self) -> None:
        """Ensure findings inside to_dict() are plain dicts, not dataclass instances."""
        report = self._make_report()
        d = report.to_dict()
        for f in d["findings"]:
            assert isinstance(f, dict)
        for sr in d["source_results"]:
            assert isinstance(sr, dict)
            for f in sr["findings"]:
                assert isinstance(f, dict)


# ---------------------------------------------------------------------------
# severity_rank
# ---------------------------------------------------------------------------


class TestSeverityRank:
    @pytest.mark.parametrize(
        ("severity", "expected_rank"),
        [
            ("info", 0),
            ("low", 1),
            ("medium", 2),
            ("high", 3),
            ("critical", 4),
        ],
    )
    def test_known_severities(self, severity: str, expected_rank: int) -> None:
        assert severity_rank(severity) == expected_rank

    def test_ordering_critical_gt_high(self) -> None:
        assert severity_rank("critical") > severity_rank("high")

    def test_ordering_high_gt_medium(self) -> None:
        assert severity_rank("high") > severity_rank("medium")

    def test_ordering_medium_gt_low(self) -> None:
        assert severity_rank("medium") > severity_rank("low")

    def test_ordering_low_gt_info(self) -> None:
        assert severity_rank("low") > severity_rank("info")

    def test_unknown_severity_maps_to_zero(self) -> None:
        assert severity_rank("unknown") == 0
        assert severity_rank("bogus") == 0

    def test_case_insensitive(self) -> None:
        assert severity_rank("CRITICAL") == 4
        assert severity_rank("High") == 3
        assert severity_rank("Medium") == 2
