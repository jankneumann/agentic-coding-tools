"""Tests for analysis-round merge plan production (tasks 1.2 and 1.3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from build_plan import build_plan, emit_plan, write_plan  # noqa: E402
from merge_plan import validate_plan  # noqa: E402


def analysis_inputs() -> tuple[list[dict], dict[int, dict], dict[int, dict]]:
    prs = [
        {
            "number": 20,
            "title": "Base feature",
            "branch": "feature/base",
            "base_branch": "main",
            "origin": "openspec",
            "ci_state": "clean",
        },
        {
            "number": 21,
            "title": "Stacked feature",
            "branch": "feature/stacked",
            "base_branch": "feature/base",
            "origin": "codex",
            "ci_state": "unstable",
        },
        {
            "number": 22,
            "title": "Dependency bump",
            "branch": "dependabot/pip/example-2",
            "base_branch": "main",
            "origin": "dependabot",
            "ci_state": "clean",
        },
    ]
    staleness = {
        20: {"staleness": "fresh", "pr_files": ["src/shared.py"]},
        21: {"staleness": "stale", "pr_files": ["src/stack.py"]},
        22: {"staleness": "fresh", "pr_files": ["src/shared.py"]},
    }
    comments = {
        20: {"unresolved_count": 1},
        21: {"unresolved_count": 0},
        22: {"unresolved_count": 0},
    }
    return prs, staleness, comments


def test_build_plan_maps_analysis_state_and_initializes_pending_outcomes() -> None:
    prs, staleness, comments = analysis_inputs()

    plan = build_plan(prs, staleness, comments, generated_at="2026-08-19T12:00:00+00:00")

    validate_plan(plan)
    nodes = {node["pr"]: node for node in plan["nodes"]}
    assert nodes[20]["state"]["outcome"] == "pending"
    assert nodes[20]["state"]["staleness"] == "fresh"
    assert nodes[20]["state"]["ci_state"] == "clean"
    assert nodes[20]["state"]["unresolved_comments"] == 1
    assert nodes[22]["auto_executable"] is True
    assert nodes[20]["auto_executable"] is False
    assert nodes[20]["definition"]["gates"] == ["proposal_acceptance"]


def test_build_plan_does_not_trust_caller_auto_execution_for_openspec() -> None:
    prs, staleness, comments = analysis_inputs()
    prs[0]["auto_executable"] = True
    prs[0]["gates"] = []

    plan = build_plan(
        prs,
        staleness,
        comments,
        generated_at="2026-08-19T12:00:00+00:00",
    )

    node = plan["nodes"][0]
    assert node["auto_executable"] is False
    assert node["definition"]["gates"] == ["proposal_acceptance"]


def test_build_plan_derives_base_branch_and_file_overlap_edges() -> None:
    prs, staleness, comments = analysis_inputs()

    plan = build_plan(prs, staleness, comments, generated_at="2026-08-19T12:00:00+00:00")

    nodes = {node["pr"]: node for node in plan["nodes"]}
    assert nodes[21]["definition"]["depends_on"] == [20]
    assert 20 in nodes[22]["definition"]["depends_on"]


def test_write_plan_persists_schema_valid_json(tmp_path: Path) -> None:
    prs, staleness, comments = analysis_inputs()
    plan = build_plan(prs, staleness, comments, generated_at="2026-08-19T12:00:00+00:00")
    destination = tmp_path / "merge-plan.json"

    write_plan(plan, destination)

    written = json.loads(destination.read_text(encoding="utf-8"))
    assert written == plan
    validate_plan(written)


def test_emit_plan_writes_json_and_markdown_projection(tmp_path: Path) -> None:
    prs, staleness, comments = analysis_inputs()
    plan = build_plan(prs, staleness, comments, generated_at="2026-08-19T12:00:00+00:00")
    destination = tmp_path / "merge-plan.json"

    projection = emit_plan(plan, destination)

    assert destination.exists()
    assert projection == tmp_path / "merge-plan.md"
    assert "| #20 | Base feature | openspec | pending |" in projection.read_text(
        encoding="utf-8",
    )


def test_emit_plan_recovers_consistent_projection_after_second_replace_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from build_plan import _replace_bundle_member
    from plan_storage import FilePlanStore

    prs, staleness, comments = analysis_inputs()
    original = build_plan(
        prs,
        staleness,
        comments,
        generated_at="2026-08-19T12:00:00+00:00",
    )
    destination = tmp_path / "merge-plan.json"
    emit_plan(original, destination)
    changed = json.loads(json.dumps(original))
    changed["nodes"][0]["state"]["blocking_reason"] = "new blocker"
    replacements = 0

    def fail_json_commit(source: Path, target: Path) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated JSON commit failure")
        _replace_bundle_member(source, target)

    monkeypatch.setattr("build_plan._replace_bundle_member", fail_json_commit)

    with pytest.raises(OSError, match="JSON commit failure"):
        emit_plan(changed, destination)

    loaded = FilePlanStore(destination).load()
    assert loaded == original
    projection = destination.with_suffix(".md").read_text(encoding="utf-8")
    assert "new blocker" not in projection
