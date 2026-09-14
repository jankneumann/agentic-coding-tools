"""Candidate-work projection tests for improve-harness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from improve_candidate_work import project_candidate_work, write_projection
from candidate_work import (
    CandidateWorkValidationError,
    load_candidate_work,
    write_candidate_work,
)


def _finding(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "capability_gap": "Slow lock acquisition",
        "frequency": 2,
        "max_severity": "high",
        "score": 6,
        "affected_skills": ["implement-feature", "validate-feature"],
        "sources": ["self-reported"],
        "entries": [{"id": "memory-immutable-1"}, {"id": "memory-immutable-2"}],
    }
    result.update(overrides)
    return result


def test_projects_ranked_gaps_with_priority_effort_and_source_rank() -> None:
    candidates = project_candidate_work([_finding()], "reports/gaps.md")
    candidate = candidates[0]
    assert candidate["priority"] == 2
    assert candidate["effort"] == "M"
    assert candidate["tags"] == ["source-rank-1"]
    assert candidate["provenance"] == {
        "source_artifact": "reports/gaps.md",
        "finding_ids": ["memory-immutable-1", "memory-immutable-2"],
        "generator": "improve-harness",
    }


def test_max_severity_is_normalized_case_insensitively() -> None:
    candidate = project_candidate_work(
        [_finding(max_severity=" HIGH ")], "reports/gaps.md"
    )[0]

    assert candidate["priority"] == 2
    assert "maximum severity high" in candidate["rationale"]


def test_missing_affected_skills_defaults_effort_and_tags_reason() -> None:
    candidate = project_candidate_work(
        [_finding(affected_skills=None)], "reports/gaps.md"
    )[0]
    assert candidate["effort"] == "M"
    assert candidate["tags"] == ["source-rank-1", "effort-estimate-default"]


def test_id_survives_report_and_rank_changes() -> None:
    first = project_candidate_work([_finding()], "first.md")[0]
    reranked = project_candidate_work(
        [_finding(score=99, frequency=8, max_severity="critical")], "second.md"
    )[0]
    assert first["suggested_change_id"] == reranked["suggested_change_id"]


def test_write_projection_produces_schema_valid_batch(tmp_path: Path) -> None:
    destination = tmp_path / "improve-harness-candidate-work.json"
    write_projection([_finding()], destination, "reports/gaps.md")
    loaded = load_candidate_work(destination)
    assert isinstance(loaded, list)
    assert loaded[0]["provenance"]["generator"] == "improve-harness"


def test_cli_file_report_writes_adjacent_candidate_sidecar(
    tmp_path: Path, monkeypatch
) -> None:
    import analyze_failures
    import generate_report

    entries = [
        {
            "id": "memory-immutable-1",
            "tags": [
                "capability_gap:Slow lock acquisition",
                "affected_skill:implement-feature",
                "severity:high",
                "source:self-reported",
            ],
        }
    ]
    monkeypatch.setattr(analyze_failures, "query_memory", lambda **_kwargs: entries)
    report_path = tmp_path / "capability-gaps.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_report.py", "--output", str(report_path)],
    )

    generate_report.main()

    destination = tmp_path / "improve-harness-candidate-work.json"
    loaded = load_candidate_work(destination)
    assert isinstance(loaded, list)
    assert loaded[0]["provenance"]["source_artifact"] == str(report_path)


def test_explicit_hint_is_normalized_without_identity_suffix() -> None:
    candidate = project_candidate_work(
        [_finding(suggested_change_id="Fix Lock Acquisition")], "report.md"
    )[0]
    assert candidate["suggested_change_id"] == "update-lock-acquisition"


def test_stdout_only_cli_remains_write_free(tmp_path: Path, monkeypatch) -> None:
    import analyze_failures
    import generate_report

    monkeypatch.setattr(analyze_failures, "query_memory", lambda **_kwargs: [])
    monkeypatch.setattr(sys, "argv", ["generate_report.py"])
    monkeypatch.chdir(tmp_path)

    generate_report.main()

    assert not (tmp_path / "improve-harness-candidate-work.json").exists()


def test_equal_severity_uses_affected_skill_effort_bands() -> None:
    findings = [
        _finding(capability_gap="One", affected_skills=["one"]),
        _finding(capability_gap="Two", affected_skills=["one", "two"]),
        _finding(capability_gap="Three", affected_skills=["one", "two", "three"]),
        _finding(
            capability_gap="Four",
            affected_skills=["one", "two", "three", "four"],
        ),
    ]

    candidates = project_candidate_work(findings, "reports/gaps.md")

    assert [candidate["priority"] for candidate in candidates] == [2, 2, 2, 2]
    assert [candidate["effort"] for candidate in candidates] == ["S", "M", "M", "L"]


def _run_file_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ranked: list[dict[str, object]],
    *,
    candidate_path: Path | None = None,
) -> tuple[int, Path, Path]:
    import analyze_failures
    import generate_report

    monkeypatch.setattr(analyze_failures, "query_memory", lambda **_kwargs: [{}])
    monkeypatch.setattr(analyze_failures, "rank_findings", lambda _entries: ranked)
    report_path = tmp_path / "capability-gaps.md"
    destination = candidate_path or tmp_path / "improve-harness-candidate-work.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_report.py",
            "--output",
            str(report_path),
            "--candidate-work-output",
            str(destination),
        ],
    )
    return generate_report.main(), report_path, destination


def test_cli_collision_is_concise_and_preserves_report_and_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "candidate-work.json"
    other = project_candidate_work([_finding()], "other-report.md")[0]
    other["provenance"]["generator"] = "bug-scrub"
    write_candidate_work(destination, [other], generator="bug-scrub")
    before = destination.read_bytes()

    result, report_path, _ = _run_file_cli(
        tmp_path,
        monkeypatch,
        [_finding()],
        candidate_path=destination,
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "bug-scrub" in captured.err
    assert "Traceback" not in captured.err
    assert report_path.exists()
    assert destination.read_bytes() == before


def test_cli_schema_failure_is_concise_and_preserves_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import improve_candidate_work

    def fail_validation(*_args, **_kwargs):
        raise CandidateWorkValidationError(
            ["title: should be non-empty"], index=0
        )

    monkeypatch.setattr(improve_candidate_work, "write_projection", fail_validation)

    result, report_path, destination = _run_file_cli(
        tmp_path, monkeypatch, [_finding()]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("error: candidate-work sidecar not written:")
    assert "title" in captured.err
    assert "Traceback" not in captured.err
    assert report_path.exists()
    assert not destination.exists()


def test_cli_projection_value_error_is_concise_and_preserves_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import improve_candidate_work

    def fail_projection(*_args, **_kwargs):
        raise ValueError("projection failed")

    monkeypatch.setattr(improve_candidate_work, "write_projection", fail_projection)

    result, report_path, destination = _run_file_cli(
        tmp_path, monkeypatch, [_finding()]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err == "error: candidate-work sidecar not written: projection failed\n"
    assert "Traceback" not in captured.err
    assert report_path.exists()
    assert not destination.exists()


def test_cli_unknown_max_severity_is_concise_and_preserves_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, report_path, destination = _run_file_cli(
        tmp_path,
        monkeypatch,
        [_finding(max_severity="urgent")],
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err == (
        "error: candidate-work sidecar not written: "
        "unsupported improve-harness max_severity: 'urgent'\n"
    )
    assert "Traceback" not in captured.err
    assert report_path.exists()
    assert not destination.exists()
