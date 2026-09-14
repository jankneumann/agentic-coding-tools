"""Candidate-work projection tests for improve-harness."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from improve_candidate_work import project_candidate_work, write_projection
from candidate_work import load_candidate_work


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
