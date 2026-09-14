"""Cross-skill candidate projection, ranking, and approved intake flow."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = REPO_ROOT / "skills"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bug_projection(destination: Path) -> None:
    scripts = SKILLS / "bug-scrub" / "scripts"
    saved_models = sys.modules.pop("models", None)
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(scripts))
        models = _load_module("models", scripts / "models.py")
        projector = _load_module(
            "_candidate_flow_bug_projection", scripts / "bug_candidate_work.py"
        )
        finding = models.Finding(
            id="marker-src-main-py-1",
            source="markers",
            severity="high",
            category="code-marker",
            title="Remove stale marker",
            detail="Delete the obsolete marker.",
            file_path="src/main.py",
            line=1,
        )
        report = models.BugScrubReport(
            timestamp="2026-09-13T00:00:00Z",
            sources_used=["markers"],
            severity_filter="low",
            findings=[finding],
        )
        projector.write_projection(report, destination, "reports/bug-scrub.json")
    finally:
        sys.path[:] = original_path
        sys.modules.pop("models", None)
        if saved_models is not None:
            sys.modules["models"] = saved_models


def _candidate_intake_module() -> ModuleType:
    scripts = SKILLS / "plan-roadmap" / "scripts"
    generic_names = ("decomposer", "models", "refiner", "scaffolder")
    saved = {name: sys.modules.pop(name, None) for name in generic_names}
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(scripts))
        return _load_module(
            "_candidate_flow_intake", scripts / "candidate_intake.py"
        )
    finally:
        sys.path[:] = original_path
        for name in generic_names:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


def _copy_schemas(repo_root: Path) -> None:
    schemas = repo_root / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in ("candidate-work.schema.json", "roadmap.schema.json"):
        shutil.copy(REPO_ROOT / "openspec" / "schemas" / name, schemas / name)
    (repo_root / "openspec" / "changes").mkdir()


def test_producers_rank_twice_then_preview_and_create_approved_roadmaps(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _copy_schemas(repo_root)
    sidecars = tmp_path / "sidecars"
    sidecars.mkdir()

    bug_path = sidecars / "bug.json"
    _bug_projection(bug_path)

    improve = _load_module(
        "_candidate_flow_improve",
        SKILLS / "improve-harness" / "scripts" / "improve_candidate_work.py",
    )
    improve_path = sidecars / "improve.json"
    improve.write_projection(
        [
            {
                "capability_gap": "Retry control",
                "frequency": 2,
                "max_severity": "high",
                "affected_skills": ["implement-feature"],
                "entries": [{"id": "gap-retry-1"}],
            }
        ],
        improve_path,
        "reports/improve-harness.json",
    )

    explore = _load_module(
        "_candidate_flow_explore",
        SKILLS / "explore-feature" / "scripts" / "candidate_projection.py",
    )
    opportunities = repo_root / "docs" / "feature-discovery" / "opportunities.json"
    opportunities.parent.mkdir(parents=True)
    opportunities.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "already-tracked",
                        "title": "Existing work",
                        "suggested_change_prefix": "(existing)",
                    },
                    {
                        "id": "trace-view",
                        "title": "Add trace view",
                        "description": "Show candidate provenance.",
                        "rationale": "Operators need an end-to-end view.",
                        "suggested_change_id": "add-trace-view",
                        "impact": "high",
                        "strategic_fit": "high",
                        "effort": "S",
                        "risk": "low",
                        "focus_match": 1,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    explore_path = sidecars / "explore.json"
    explore.run(opportunities, explore_path)

    lane = _load_module(
        "_candidate_flow_lane",
        SKILLS / "prioritize-proposals" / "scripts" / "candidate_lane.py",
    )
    paths = [bug_path, improve_path, explore_path]
    first = lane.rank_candidate_work(lane.load_candidate_inputs(paths))
    second = lane.rank_candidate_work(lane.load_candidate_inputs(paths))

    assert first.to_dict() == second.to_dict()
    assert len(first.items) == 3
    by_generator = {
        item.candidate["provenance"]["generator"]: item.candidate
        for item in first.items
    }
    assert set(by_generator) == {"bug-scrub", "improve-harness", "explore-feature"}
    assert by_generator["improve-harness"]["effort"] == "S"

    intake = _candidate_intake_module()
    existing_path = repo_root / "openspec" / "roadmaps" / "existing" / "roadmap.yaml"
    intake.save_roadmap(
        intake.Roadmap(
            schema_version=1,
            roadmap_id="existing",
            source_proposal="docs/existing.md",
            status=intake.RoadmapStatus.APPROVED,
            items=[
                intake.RoadmapItem(
                    item_id="ri-01",
                    title="Existing base",
                    description="Existing approved work.",
                    rationale="Baseline.",
                    status=intake.ItemStatus.APPROVED,
                    effort=intake.Effort.S,
                    priority=1,
                    change_id="add-existing-base",
                    acceptance_outcomes=["Baseline remains available"],
                )
            ],
        ),
        existing_path,
    )
    before = existing_path.read_bytes()
    preview = intake.preview_existing_roadmap(
        by_generator["bug-scrub"],
        repo_root=repo_root,
        roadmap_path=existing_path,
        acceptance_outcomes=["The stale marker is absent"],
        actor="integration-test",
    )

    preview_item = preview.request["operations"][0]["item"]
    assert preview_item["change_id"] == by_generator["bug-scrub"]["suggested_change_id"]
    assert existing_path.read_bytes() == before

    created = intake.create_new_roadmap(
        by_generator["explore-feature"],
        repo_root=repo_root,
        roadmap_id="trace-roadmap",
        capability="trace-view",
        acceptance_outcomes=["Candidate provenance is visible"],
    )

    assert created.roadmap.source_proposal == str(opportunities)
    assert created.roadmap.items[0].change_id == "add-trace-view"
    assert created.change_dir.exists()
