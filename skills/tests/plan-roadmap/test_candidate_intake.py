from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import candidate_intake
from candidate_intake import (
    CandidateIntakeError,
    build_new_roadmap,
    create_new_roadmap,
    next_free_item_id,
    preview_existing_roadmap,
)
from models import (
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    load_roadmap,
    save_roadmap,
)
from refiner import BaseRoadmapChangedError, apply_refinement

REPO_ROOT = Path(__file__).resolve().parents[3]


def _candidate(change_id: str = "update-context-index") -> dict[str, object]:
    return {
        "schema_version": 1,
        "title": "Refresh context index",
        "description": "Regenerate the checked-in project context index.",
        "rationale": "The checked-in index is stale.",
        "provenance": {
            "source_artifact": "docs/context/index.md",
            "finding_ids": ["stale-index"],
            "generator": "explore-feature",
        },
        "effort": "S",
        "priority": 7,
        "suggested_change_id": change_id,
        "depends_on": [],
    }


def _item(
    item_id: str,
    change_id: str,
    priority: int,
    status: ItemStatus = ItemStatus.APPROVED,
) -> RoadmapItem:
    return RoadmapItem(
        item_id=item_id,
        title=change_id.replace("-", " ").title(),
        description=f"Implement {change_id}.",
        rationale=f"Needed for {change_id}.",
        status=status,
        effort=Effort.S,
        priority=priority,
        change_id=change_id,
        acceptance_outcomes=[f"{change_id} works"],
    )


def _repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    schemas = repo_root / "openspec/schemas"
    schemas.mkdir(parents=True)
    for name in ("roadmap.schema.json", "candidate-work.schema.json"):
        shutil.copy(REPO_ROOT / "openspec/schemas" / name, schemas)
    return repo_root


def _write_roadmap(repo_root: Path, roadmap_id: str, items: list[RoadmapItem]) -> Path:
    path = repo_root / "openspec/roadmaps" / roadmap_id / "roadmap.yaml"
    save_roadmap(
        Roadmap(
            schema_version=1,
            roadmap_id=roadmap_id,
            source_proposal=f"docs/{roadmap_id}.md",
            status=RoadmapStatus.APPROVED,
            items=items,
        ),
        path,
    )
    return path


def _preview(candidate: object, repo_root: Path, path: Path):
    return preview_existing_roadmap(
        candidate,
        repo_root=repo_root,
        roadmap_path=path,
        acceptance_outcomes=["The context index is current"],
        actor="supervisor",
    )


def test_new_roadmap_preserves_source_capability_and_candidate_fields(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    roadmap = build_new_roadmap(
        _candidate(),
        repo_root=repo_root,
        roadmap_id="context-refresh",
        capability="context-index",
        acceptance_outcomes=["The context index is current"],
    )

    item = roadmap.items[0]
    assert (roadmap.schema_version, roadmap.status) == (1, RoadmapStatus.APPROVED)
    assert roadmap.source_proposal == "docs/context/index.md"
    assert (item.item_id, item.change_id, item.capability) == (
        "ri-01",
        "update-context-index",
        "context-index",
    )
    assert (item.title, item.rationale, item.effort, item.priority) == (
        "Refresh context index",
        "The checked-in index is stale.",
        Effort.S,
        7,
    )
    assert "explore-feature" in item.description
    assert "docs/context/index.md" in item.description


def test_new_roadmap_save_is_no_overwrite_and_scaffolds_capability(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    result = create_new_roadmap(
        _candidate(),
        repo_root=repo_root,
        roadmap_id="context-refresh",
        capability="context-index",
        acceptance_outcomes=["The context index is current"],
    )

    assert result.roadmap_path.exists()
    assert result.change_dir == repo_root / "openspec/changes/update-context-index"
    assert (result.change_dir / "specs/context-index/spec.md").exists()
    with pytest.raises((CandidateIntakeError, FileExistsError), match="exists"):
        create_new_roadmap(
            _candidate(),
            repo_root=repo_root,
            roadmap_id="context-refresh",
            capability="context-index",
            acceptance_outcomes=["The context index is current"],
        )


def test_new_roadmap_rejects_duplicate_semantic_roadmap_id(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    existing_path = (
        repo_root / "openspec/roadmaps/different-directory/roadmap.yaml"
    )
    save_roadmap(
        Roadmap(
            schema_version=1,
            roadmap_id="context-refresh",
            source_proposal="docs/existing.md",
            status=RoadmapStatus.APPROVED,
            items=[_item("ri-01", "add-existing", 1)],
        ),
        existing_path,
    )

    with pytest.raises(CandidateIntakeError, match="roadmap ID.*already exists"):
        create_new_roadmap(
            _candidate(),
            repo_root=repo_root,
            roadmap_id="context-refresh",
            capability="context-index",
            acceptance_outcomes=["The context index is current"],
        )

    assert not (repo_root / "openspec/roadmaps/context-refresh").exists()
    assert not (repo_root / "openspec/changes/update-context-index").exists()


def test_new_roadmap_does_not_overwrite_change_appearing_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = _repo(tmp_path)
    destination = repo_root / "openspec/changes/update-context-index"
    sentinel = destination / "proposal.md"
    original_lifecycle_records = candidate_intake._lifecycle_records

    def introduce_active_change(root: Path):
        records = original_lifecycle_records(root)
        destination.mkdir(parents=True)
        sentinel.write_text("existing active work", encoding="utf-8")
        return records

    monkeypatch.setattr(
        candidate_intake, "_lifecycle_records", introduce_active_change
    )

    with pytest.raises(CandidateIntakeError, match="already exists"):
        create_new_roadmap(
            _candidate(),
            repo_root=repo_root,
            roadmap_id="context-refresh",
            capability="context-index",
            acceptance_outcomes=["The context index is current"],
        )

    assert sentinel.read_text(encoding="utf-8") == "existing active work"
    assert not (repo_root / "openspec/roadmaps/context-refresh").exists()


def test_new_roadmap_scaffold_failure_leaves_no_partial_roadmap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = _repo(tmp_path)

    def fail_scaffold(*_args, **_kwargs):
        raise OSError("simulated scaffold failure")

    monkeypatch.setattr(candidate_intake, "scaffold_change", fail_scaffold)

    with pytest.raises(OSError, match="simulated scaffold failure"):
        create_new_roadmap(
            _candidate(),
            repo_root=repo_root,
            roadmap_id="context-refresh",
            capability="context-index",
            acceptance_outcomes=["The context index is current"],
        )

    assert not (repo_root / "openspec/roadmaps/context-refresh").exists()
    assert not (repo_root / "openspec/changes/update-context-index").exists()


def test_existing_preview_uses_fresh_monotonic_id_and_refiner_priority(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    path = _write_roadmap(
        repo_root,
        "target",
        [_item("ri-01", "add-one", 3), _item("ri-03", "add-three", 8)],
    )
    before = path.read_bytes()
    result = _preview(_candidate(), repo_root, path)

    assert len(result.request["operations"]) == 1
    item = result.request["operations"][0]["item"]
    assert (result.request["operations"][0]["op"], item["item_id"]) == ("add", "ri-04")
    assert item["change_id"] == "update-context-index"
    assert "priority" not in item
    assert "Candidate priority: 7" in result.request["rationale"]
    assert result.request["source"] == "docs/context/index.md"
    assert result.preview.candidate["items"][-1]["priority"] == 9
    assert not (repo_root / "openspec/changes/update-context-index").exists()
    assert path.read_bytes() == before


def test_existing_preview_retries_when_base_changes_before_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = _repo(tmp_path)
    path = _write_roadmap(
        repo_root,
        "target",
        [_item("ri-01", "add-one", 3)],
    )
    original_preview = candidate_intake.preview_refinement
    calls = 0

    def interleaved_preview(
        roadmap_path: Path, request: dict[str, object], root: Path
    ):
        nonlocal calls
        calls += 1
        if calls == 1:
            concurrent = load_roadmap(roadmap_path, root)
            concurrent.items.append(_item("ri-05", "add-concurrent", 8))
            save_roadmap(concurrent, roadmap_path, overwrite=True)
        return original_preview(roadmap_path, request, root)

    monkeypatch.setattr(
        candidate_intake, "preview_refinement", interleaved_preview
    )

    result = _preview(_candidate(), repo_root, path)

    assert calls == 2
    assert result.request["operations"][0]["item"]["item_id"] == "ri-06"
    assert result.preview.candidate["items"][-1]["priority"] == 9


def test_next_free_item_id_expands_past_two_digits() -> None:
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="target",
        source_proposal="source",
        items=[_item("ri-99", "add-existing", 1)],
    )
    assert next_free_item_id(roadmap) == "ri-100"


def test_dependencies_map_local_external_and_completed(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    target = _write_roadmap(repo_root, "target", [_item("ri-01", "add-local", 1)])
    _write_roadmap(repo_root, "other", [_item("ri-02", "add-external", 1)])
    _write_roadmap(
        repo_root,
        "history",
        [_item("ri-03", "add-done", 1, ItemStatus.COMPLETED)],
    )
    (repo_root / "openspec/changes/add-local").mkdir(parents=True)
    (repo_root / "openspec/changes/add-external").mkdir(parents=True)
    (repo_root / "openspec/changes/archive/2026-09-13-add-done").mkdir(parents=True)
    candidate = _candidate()
    candidate["depends_on"] = ["add-local", "add-external", "add-done"]

    item = _preview(candidate, repo_root, target).request["operations"][0]["item"]

    assert item["depends_on"] == ["ri-01"]
    assert item["external_depends_on"] == ["other:ri-02"]
    assert "Resolved dependency: add-local -> ri-01" in item["rationale"]
    assert (
        "Resolved dependency: add-external -> other:ri-02"
        in item["rationale"]
    )
    assert item["rationale"].count(
        "Satisfied dependency: add-done (completed)"
    ) == 1


@pytest.mark.parametrize(
    ("dependency", "setup"),
    [("add-unknown", None), ("add-orphan", "active"), ("add-failed", "failed")],
)
def test_unresolved_dependencies_fail(
    tmp_path: Path, dependency: str, setup: str | None
) -> None:
    repo_root = _repo(tmp_path)
    target = _write_roadmap(repo_root, "target", [_item("ri-01", "add-existing", 1)])
    if setup == "active":
        (repo_root / "openspec/changes/add-orphan").mkdir(parents=True)
    if setup == "failed":
        _write_roadmap(
            repo_root,
            "history",
            [_item("ri-02", "add-failed", 1, ItemStatus.FAILED)],
        )
    candidate = _candidate()
    candidate["depends_on"] = [dependency]

    with pytest.raises(CandidateIntakeError, match=dependency):
        _preview(candidate, repo_root, target)


def test_multiple_live_dependency_owners_are_ambiguous(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    target = _write_roadmap(repo_root, "target", [_item("ri-01", "add-existing", 1)])
    _write_roadmap(repo_root, "one", [_item("ri-01", "add-shared", 1)])
    _write_roadmap(repo_root, "two", [_item("ri-01", "add-shared", 1)])
    candidate = _candidate()
    candidate["depends_on"] = ["add-shared"]

    with pytest.raises(CandidateIntakeError, match="ambiguous"):
        _preview(candidate, repo_root, target)


def test_blank_outcomes_and_batch_or_collision_fail_before_writes(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    with pytest.raises(CandidateIntakeError, match="acceptance outcome"):
        create_new_roadmap(
            _candidate(),
            repo_root=repo_root,
            roadmap_id="context-refresh",
            capability="context-index",
            acceptance_outcomes=["  "],
        )
    assert not (repo_root / "openspec/roadmaps/context-refresh").exists()

    target = _write_roadmap(
        repo_root, "target", [_item("ri-01", "update-context-index", 1)]
    )
    with pytest.raises(CandidateIntakeError, match="exactly one"):
        build_new_roadmap(
            [_candidate()],
            repo_root=repo_root,
            roadmap_id="new-roadmap",
            capability="context-index",
            acceptance_outcomes=["It works"],
        )
    with pytest.raises(CandidateIntakeError, match="already exists"):
        _preview(_candidate(), repo_root, target)



@pytest.mark.parametrize("location", ["active", "archive"])
def test_change_id_collision_in_active_or_archive_fails(
    tmp_path: Path, location: str
) -> None:
    repo_root = _repo(tmp_path)
    target = _write_roadmap(repo_root, "target", [_item("ri-01", "add-existing", 1)])
    changes = repo_root / "openspec/changes"
    destination = (
        changes / "update-context-index"
        if location == "active"
        else changes / "archive/2026-09-13-update-context-index"
    )
    destination.mkdir(parents=True)

    with pytest.raises(CandidateIntakeError, match="already exists"):
        _preview(_candidate(), repo_root, target)


def test_apply_rejects_stale_roadmap_after_candidate_preview(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    path = _write_roadmap(repo_root, "target", [_item("ri-01", "add-existing", 1)])
    result = _preview(_candidate(), repo_root, path)
    current = yaml.safe_load(path.read_text(encoding="utf-8"))
    current["items"].append(_item("ri-02", "add-concurrent", 2).to_dict())
    path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")

    with pytest.raises(BaseRoadmapChangedError):
        apply_refinement(
            path,
            result.request,
            repo_root,
            expected_base_sha256=result.preview.base_sha256,
        )
