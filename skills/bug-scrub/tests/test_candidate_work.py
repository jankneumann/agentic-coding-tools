"""Candidate-work projection tests for bug-scrub."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from bug_candidate_work import project_candidate_work, write_projection
from candidate_work import load_candidate_work
from models import BugScrubReport, Finding


def _report(*findings: Finding) -> BugScrubReport:
    return BugScrubReport(
        timestamp="2026-09-13T00:00:00Z",
        sources_used=["pytest"],
        severity_filter="info",
        findings=list(findings),
    )


def _finding(**overrides: object) -> Finding:
    values = {
        "id": "pytest-node::test_regression",
        "source": "pytest",
        "severity": "high",
        "category": "test-failure",
        "title": "Regression fails",
        "detail": "Assertion mismatch",
        "file_path": "tests/test_regression.py",
        "line": 12,
    }
    values.update(overrides)
    return Finding(**values)  # type: ignore[arg-type]


def test_projects_every_filtered_finding_with_exact_mappings(tmp_path: Path) -> None:
    report = _report(
        _finding(),
        _finding(id="marker-1", severity="info", category="code-marker"),
        _finding(id="security-1", severity="critical", category="security"),
    )
    candidates = project_candidate_work(report, "docs/bug-scrub/bug-scrub-report.json")

    assert [(item["priority"], item["effort"]) for item in candidates] == [
        (2, "S"),
        (5, "XS"),
        (1, "M"),
    ]
    assert candidates[0]["provenance"] == {
        "source_artifact": "docs/bug-scrub/bug-scrub-report.json",
        "finding_ids": ["pytest-node::test_regression"],
        "generator": "bug-scrub",
    }


def test_id_is_stable_when_mutable_finding_text_changes() -> None:
    original = project_candidate_work(_report(_finding()), "old/report.json")[0]
    changed = project_candidate_work(
        _report(_finding(title="Renamed", detail="new", file_path="elsewhere.py")),
        "new/report.json",
    )[0]
    assert original["suggested_change_id"] == changed["suggested_change_id"]


def test_unknown_category_rejects_whole_batch_without_replacing_file(tmp_path: Path) -> None:
    destination = tmp_path / "bug-scrub-candidate-work.json"
    destination.write_text('[{"owned": "before"}]\n')
    finding = _finding(category="new-category")

    with pytest.raises(ValueError, match="unsupported bug-scrub category"):
        write_projection(_report(finding), destination, "report.json")

    assert destination.read_text() == '[{"owned": "before"}]\n'


def test_empty_success_replaces_stale_owned_batch(tmp_path: Path) -> None:
    destination = tmp_path / "bug-scrub-candidate-work.json"
    write_projection(_report(_finding()), destination, "report.json")
    write_projection(_report(), destination, "report.json")
    assert json.loads(destination.read_text()) == []
    assert load_candidate_work(destination) == []


def test_normal_run_writes_adjacent_candidate_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as bug_main
    from models import SourceResult

    monkeypatch.setitem(
        bug_main.ALL_SOURCES,
        "fake",
        lambda _project: SourceResult(
            source="fake", status="ok", findings=[_finding()]
        ),
    )
    out_dir = tmp_path / "reports"
    result = bug_main.run(
        sources=["fake"],
        severity="info",
        project_dir=str(tmp_path),
        out_dir=str(out_dir),
        fmt="json",
    )

    assert result == 1
    loaded = load_candidate_work(out_dir / "bug-scrub-candidate-work.json")
    assert isinstance(loaded, list)
    assert loaded[0]["provenance"]["source_artifact"].endswith(
        "bug-scrub-report.json"
    )
