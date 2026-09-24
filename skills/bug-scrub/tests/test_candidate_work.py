"""Candidate-work projection tests for bug-scrub."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

import bug_candidate_work as projection
from bug_candidate_work import project_candidate_work, write_projection
from candidate_work import load_candidate_work, write_candidate_work
from models import BugScrubReport, Finding, FindingOrigin


def _load_bug_main() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_bug_scrub_candidate_work_main", SCRIPTS / "main.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _project(finding: Finding) -> list[dict[str, object]]:
    return project_candidate_work(_report(finding), "report.json")


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


def test_id_is_stable_across_line_shifts_report_paths_and_collector_order() -> None:
    original = _finding(
        id="mypy-arg-type-test_regression.py:12",
        source="mypy",
        category="type-error",
        title="Argument incompatible",
        detail="tests/test_regression.py:12: error: Argument incompatible [arg-type]",
        line=12,
    )
    shifted = _finding(
        id="mypy-arg-type-test_regression.py:41",
        source="mypy",
        category="type-error",
        title="Renamed diagnostic",
        detail="tests/test_regression.py:41: error: Argument incompatible [arg-type]",
        line=41,
    )
    other = _finding(
        id="arch-coupling-0",
        source="architecture",
        category="architecture",
        detail="Layer cycle detected",
        file_path="src/other.py",
    )

    first = project_candidate_work(_report(original, other), "old/report.json")
    reordered = project_candidate_work(
        _report(other, shifted), "new/report.json"
    )

    assert first[0]["suggested_change_id"] == reordered[1]["suggested_change_id"]
    assert first[0]["provenance"]["finding_ids"] == [original.id]
    assert reordered[1]["provenance"]["finding_ids"] == [shifted.id]


def test_same_line_semantically_distinct_findings_get_distinct_ids() -> None:
    candidates = project_candidate_work(
        _report(
            _finding(
                id="ruff-E501-same.py:12",
                source="ruff",
                category="lint",
                detail="Line too long",
                file_path="same.py",
                line=12,
            ),
            _finding(
                id="ruff-F821-same.py:12",
                source="ruff",
                category="lint",
                detail="Undefined name",
                file_path="same.py",
                line=12,
            ),
        ),
        "report.json",
    )

    assert candidates[0]["suggested_change_id"] != candidates[1]["suggested_change_id"]


def test_distinct_pytest_nodes_with_empty_detail_get_distinct_ids() -> None:
    candidates = project_candidate_work(
        _report(
            _finding(
                id="pytest-test_first",
                source="pytest",
                title="Test failure: test_first",
                detail="",
                file_path="tests/test_same.py",
            ),
            _finding(
                id="pytest-test_second",
                source="pytest",
                title="Test failure: test_second",
                detail="",
                file_path="tests/test_same.py",
            ),
        ),
        "report.json",
    )

    assert candidates[0]["suggested_change_id"] != candidates[1]["suggested_change_id"]


def test_internal_path_whitespace_is_semantic() -> None:
    compact = project_candidate_work(
        _report(_finding(id="stable", source="custom", file_path="src/a b.py")),
        "report.json",
    )[0]
    doubled = project_candidate_work(
        _report(_finding(id="stable", source="custom", file_path="src/a  b.py")),
        "report.json",
    )[0]

    assert compact["suggested_change_id"] != doubled["suggested_change_id"]


def test_semantic_detail_does_not_strip_a_basename_only_prefix() -> None:
    basename = project_candidate_work(
        _report(
            _finding(
                id="stable",
                source="custom",
                file_path="src/test_same.py",
                detail="test_same.py:12: error: failure",
            )
        ),
        "report.json",
    )[0]
    plain = project_candidate_work(
        _report(
            _finding(
                id="stable",
                source="custom",
                file_path="src/test_same.py",
                detail="error: failure",
            )
        ),
        "report.json",
    )[0]

    assert basename["suggested_change_id"] != plain["suggested_change_id"]


def test_semantic_detail_strips_full_path_line_without_line_metadata() -> None:
    prefixed = project_candidate_work(
        _report(
            _finding(
                id="stable",
                source="custom",
                file_path="src/test_same.py",
                line=None,
                detail="src/test_same.py:12: error: failure",
            )
        ),
        "report.json",
    )[0]
    plain = project_candidate_work(
        _report(
            _finding(
                id="stable",
                source="custom",
                file_path="src/test_same.py",
                line=None,
                detail="error: failure",
            )
        ),
        "report.json",
    )[0]

    assert prefixed["suggested_change_id"] == plain["suggested_change_id"]


def test_repeated_equivalent_findings_are_distinct_and_stable_after_line_shifts() -> None:
    first = project_candidate_work(
        _report(
            _finding(
                id="ruff-E501-same.py:10",
                source="ruff",
                category="lint",
                detail="Line too long",
                file_path="same.py",
                line=10,
            ),
            _finding(
                id="ruff-E501-same.py:20",
                source="ruff",
                category="lint",
                detail="Line too long",
                file_path="same.py",
                line=20,
            ),
        ),
        "first.json",
    )
    shifted_and_reordered = project_candidate_work(
        _report(
            _finding(
                id="ruff-E501-same.py:21",
                source="ruff",
                category="lint",
                detail="Line too long",
                file_path="same.py",
                line=21,
            ),
            _finding(id="pytest-unrelated", detail="Different"),
            _finding(
                id="ruff-E501-same.py:11",
                source="ruff",
                category="lint",
                detail="Line too long",
                file_path="same.py",
                line=11,
            ),
        ),
        "second.json",
    )

    first_ids = [item["suggested_change_id"] for item in first]
    shifted_by_finding = {
        item["provenance"]["finding_ids"][0]: item["suggested_change_id"]
        for item in shifted_and_reordered
    }
    assert first_ids[0] != first_ids[1]
    assert first_ids == [
        shifted_by_finding["ruff-E501-same.py:11"],
        shifted_by_finding["ruff-E501-same.py:21"],
    ]


def test_semantic_detail_preserves_message_backslashes() -> None:
    with_backslashes = _project(
        _finding(
            id="stable-finding",
            source="custom",
            file_path=r"src\test.py",
            line=None,
            detail=r"src\test.py:12: error: use C:\temp\value",
        )
    )
    with_slashes = _project(
        _finding(
            id="stable-finding",
            source="custom",
            file_path=r"src\test.py",
            line=None,
            detail=r"src\test.py:12: error: use C:/temp/value",
        )
    )

    assert (
        with_backslashes[0]["suggested_change_id"]
        != with_slashes[0]["suggested_change_id"]
    )


def test_leading_whitespace_before_full_path_coordinate_is_ignored() -> None:
    prefixed = _project(
        _finding(
            id="stable-finding",
            source="custom",
            file_path="src/test.py",
            line=None,
            detail=" \t src/test.py:12: error: failure",
        )
    )
    plain = _project(
        _finding(
            id="stable-finding",
            source="custom",
            file_path="src/test.py",
            line=None,
            detail="error: failure",
        )
    )

    assert prefixed[0]["suggested_change_id"] == plain[0]["suggested_change_id"]


def test_none_paths_and_origins_are_empty_in_base_identity() -> None:
    finding = _finding(
        file_path=None,
        origin=FindingOrigin(
            change_id=cast(str, None), artifact_path=cast(str, None)
        ),
    )

    identity = projection._base_semantic_identity(finding)

    assert identity["file_path"] == ""
    assert identity["origin_artifact_path"] == ""
    assert identity["origin_change_id"] == ""


@pytest.mark.parametrize(
    ("source", "finding_id"),
    [
        ("pytest", "pytest-Test  One"),
        ("security", "sec-SCAN  42"),
        ("custom", "custom  stable"),
    ],
)
def test_stable_source_keys_preserve_exact_string(
    source: str, finding_id: str
) -> None:
    assert projection._source_key(_finding(source=source, id=finding_id)) == finding_id


def test_occurrence_fallback_uses_raw_id_and_omits_redundant_origin_path() -> None:
    finding = _finding(
        id="fallback  exact",
        line=None,
        detail="No coordinate",
        origin=FindingOrigin(
            change_id="change-id",
            artifact_path="path/identical/within/group.json",
            task_number="task-7",
        ),
    )

    assert projection._source_position(finding) == (
        True,
        0,
        "task-7",
        "fallback  exact",
    )


def test_semantic_source_id_hash_collision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        projection,
        "_compact_source_id",
        lambda _fingerprint: "bug-finding-collision",
        raising=False,
    )

    with pytest.raises(ValueError, match="semantic source ID collision"):
        project_candidate_work(
            _report(
                _finding(id="one", detail="First semantic finding"),
                _finding(id="two", detail="Second semantic finding"),
            ),
            "report.json",
        )


def test_severity_is_normalized_and_unknown_values_are_concise() -> None:
    candidate = project_candidate_work(
        _report(_finding(severity=" HIGH ")), "report.json"
    )[0]

    assert candidate["priority"] == 2
    assert "severity-high" in candidate["tags"]

    with pytest.raises(ValueError, match=r"unsupported bug-scrub severity: 'urgent'"):
        project_candidate_work(
            _report(_finding(severity="urgent")), "report.json"
        )


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
    bug_main = _load_bug_main()
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


def test_collision_returns_concise_error_and_preserves_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bug_main = _load_bug_main()
    from models import SourceResult

    monkeypatch.setitem(
        bug_main.ALL_SOURCES,
        "fake",
        lambda _project: SourceResult(
            source="fake", status="ok", findings=[_finding()]
        ),
    )
    out_dir = tmp_path / "reports"
    destination = tmp_path / "candidate-work.json"
    other = project_candidate_work(_report(_finding()), "other-report.json")[0]
    other["provenance"]["generator"] = "improve-harness"
    write_candidate_work(destination, [other], generator="improve-harness")
    before = destination.read_bytes()

    result = bug_main.run(
        sources=["fake"],
        severity="info",
        project_dir=str(tmp_path),
        out_dir=str(out_dir),
        fmt="json",
        candidate_work_output=str(destination),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "improve-harness" in captured.err
    assert "Traceback" not in captured.err
    assert destination.read_bytes() == before
    assert (out_dir / "bug-scrub-report.json").exists()


def test_validation_failure_returns_concise_error_and_preserves_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bug_main = _load_bug_main()
    from models import SourceResult

    monkeypatch.setitem(
        bug_main.ALL_SOURCES,
        "fake-invalid",
        lambda _project: SourceResult(
            source="fake-invalid", status="ok", findings=[_finding(title="")]
        ),
    )
    out_dir = tmp_path / "reports"

    result = bug_main.run(
        sources=["fake-invalid"],
        severity="info",
        project_dir=str(tmp_path),
        out_dir=str(out_dir),
        fmt="json",
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "title" in captured.err
    assert "Traceback" not in captured.err
    assert (out_dir / "bug-scrub-report.json").exists()
    assert not (out_dir / "bug-scrub-candidate-work.json").exists()


def test_cli_unsupported_category_is_concise_and_preserves_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bug_main = _load_bug_main()
    from models import SourceResult

    monkeypatch.setitem(
        bug_main.ALL_SOURCES,
        "fake-unsupported",
        lambda _project: SourceResult(
            source="fake-unsupported",
            status="ok",
            findings=[_finding(category="new-category")],
        ),
    )
    out_dir = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--source",
            "fake-unsupported",
            "--severity",
            "info",
            "--project-dir",
            str(tmp_path),
            "--out-dir",
            str(out_dir),
            "--format",
            "json",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        bug_main.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "unsupported bug-scrub category" in captured.err
    assert "Traceback" not in captured.err
    assert (out_dir / "bug-scrub-report.json").exists()
    assert not (out_dir / "bug-scrub-candidate-work.json").exists()


def test_cli_unsupported_severity_is_concise_and_preserves_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bug_main = _load_bug_main()
    from models import SourceResult

    monkeypatch.setitem(
        bug_main.ALL_SOURCES,
        "fake-unsupported-severity",
        lambda _project: SourceResult(
            source="fake-unsupported-severity",
            status="ok",
            findings=[_finding(severity="urgent")],
        ),
    )
    out_dir = tmp_path / "reports"
    destination = tmp_path / "candidate-work.json"
    destination.write_text("owned before\n", encoding="utf-8")
    before = destination.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--source",
            "fake-unsupported-severity",
            "--severity",
            "info",
            "--project-dir",
            str(tmp_path),
            "--out-dir",
            str(out_dir),
            "--format",
            "json",
            "--candidate-work-output",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        bug_main.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "unsupported bug-scrub severity" in captured.err
    assert "urgent" in captured.err
    assert captured.err.count("\n") == 1
    assert "Traceback" not in captured.err
    assert (out_dir / "bug-scrub-report.json").exists()
    assert destination.read_bytes() == before
