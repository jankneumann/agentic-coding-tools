"""Candidate-work multi-file loading contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED = REPO_ROOT / "skills" / "shared"
sys.path.insert(0, str(SHARED))

from candidate_work import (  # noqa: E402
    CandidateWorkValidationError,
    load_candidate_work_files,
)


def _candidate(change_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "title": change_id,
        "description": f"Implement {change_id}.",
        "rationale": f"Evidence for {change_id}.",
        "provenance": {
            "source_artifact": f"reports/{change_id}.json",
            "finding_ids": [f"finding-{change_id}"],
            "generator": "bug-scrub",
        },
        "effort": "S",
        "priority": 2,
        "suggested_change_id": change_id,
    }


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_array_member_error_uses_merged_batch_index(tmp_path: Path) -> None:
    first = _write(tmp_path / "first.json", [_candidate("add-first")])
    malformed = _candidate("add-malformed")
    del malformed["title"]
    second = _write(tmp_path / "second.json", [malformed])

    with pytest.raises(CandidateWorkValidationError) as exc_info:
        load_candidate_work_files([first, second])

    assert exc_info.value.index == 1
    assert "title" in str(exc_info.value)


def test_object_error_uses_merged_batch_index(tmp_path: Path) -> None:
    first = _write(tmp_path / "first.json", [_candidate("add-first")])
    malformed = _candidate("add-malformed")
    del malformed["title"]
    second = _write(tmp_path / "second.json", malformed)

    with pytest.raises(CandidateWorkValidationError) as exc_info:
        load_candidate_work_files([first, second])

    assert exc_info.value.index == 1
    assert "title" in str(exc_info.value)
