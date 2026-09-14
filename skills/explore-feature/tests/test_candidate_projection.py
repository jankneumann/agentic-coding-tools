"""Candidate-work projection tests for explore-feature."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from candidate_projection import project_candidate_work, run
from candidate_work import load_candidate_work


def _opportunity(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "id": "opportunity-immutable-7",
        "title": "Add trace explorer",
        "description": "Expose connected trace evidence.",
        "rationale": "Operators cannot follow cross-agent work today.",
        "status": "untracked",
        "impact": "high",
        "strategic_fit": "high",
        "effort": "S",
        "risk": "low",
        "focus_match": 1,
        "lenses_applied": ["10x", "inversion"],
        "hmw_reframe": "How might we eliminate manual trace correlation?",
        "blockers": ["update-trace-schema", "waiting for design sign-off"],
    }
    result.update(overrides)
    return result


def test_projects_only_untracked_and_scores_priority_and_dependencies() -> None:
    candidates = project_candidate_work(
        {
            "opportunities": [
                _opportunity(),
                _opportunity(id="tracked", status="active"),
            ]
        },
        "docs/feature-discovery/opportunities.json",
        known_change_ids={"update-trace-schema"},
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["priority"] == 2
    assert candidate["effort"] == "S"
    assert candidate["depends_on"] == ["update-trace-schema"]
    assert "blocker:waiting for design sign-off" in candidate["tags"]
    assert candidate["provenance"]["finding_ids"] == ["opportunity-immutable-7"]


def test_real_opportunities_shape_uses_items_and_change_id_hint() -> None:
    candidate = project_candidate_work(
        {"items": [_opportunity(change_id_hint="Fix Trace UI")]},
        "docs/feature-discovery/opportunities.json",
    )[0]

    assert candidate["suggested_change_id"] == "update-trace-ui"


def test_id_survives_title_score_and_provenance_path_changes() -> None:
    first = project_candidate_work([_opportunity()], "first.json")[0]
    changed = project_candidate_work(
        [_opportunity(title="Renamed", impact="low", focus_match=0)], "second.json"
    )[0]
    assert first["suggested_change_id"] == changed["suggested_change_id"]


def test_cli_writes_adjacent_empty_batch_over_stale_output(tmp_path: Path) -> None:
    source = tmp_path / "opportunities.json"
    destination = tmp_path / "explore-feature-candidate-work.json"
    source.write_text(json.dumps({"opportunities": []}))
    destination.write_text("stale")
    assert run(source) == destination
    assert load_candidate_work(destination) == []


def test_explicit_hint_is_normalized_without_identity_suffix() -> None:
    candidate = project_candidate_work(
        [_opportunity(suggested_change_id="Fix Trace UI")], "opportunities.json"
    )[0]
    assert candidate["suggested_change_id"] == "update-trace-ui"


def test_existing_suggested_change_prefix_is_not_projected() -> None:
    candidates = project_candidate_work(
        [_opportunity(suggested_change_prefix="(existing)")],
        "opportunities.json",
    )

    assert candidates == []
