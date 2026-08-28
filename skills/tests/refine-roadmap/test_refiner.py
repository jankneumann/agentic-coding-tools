"""Behavioral contract for safe active-roadmap refinement."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from models import Roadmap, validate_against_schema
from refiner import (
    BaseRoadmapChangedError,
    RefinementValidationError,
    apply_refinement,
    preview_refinement,
)


def _item(
    item_id: str,
    *,
    status: str = "approved",
    priority: int = 1,
    depends_on: list[str] | None = None,
    change_id: str | None = None,
) -> dict:
    item = {
        "item_id": item_id,
        "title": f"Item {item_id}",
        "description": f"Deliver {item_id}",
        "rationale": f"Reason for {item_id}",
        "status": status,
        "priority": priority,
        "effort": "M",
        "depends_on": depends_on or [],
        "acceptance_outcomes": [f"{item_id} is observable"],
    }
    if change_id:
        item["change_id"] = change_id
    return item


def _write_roadmap(repo_root: Path, items: list[dict], roadmap_id: str = "active") -> Path:
    workspace = repo_root / "openspec" / "roadmaps" / roadmap_id
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / "roadmap.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 1,
        "roadmap_id": roadmap_id,
        "source_proposal": f"openspec/roadmaps/{roadmap_id}/proposal.md",
        "status": "in_progress",
        "policy": {"default_action": "wait_if_budget_exceeded"},
        "items": items,
    }, sort_keys=False))
    return path


def _request(*operations: dict) -> dict:
    return {
        "rationale": "Adjust the active roadmap after new evidence.",
        "actor": "codex",
        "source": "operator request",
        "operations": list(operations),
    }


def _new_item(item_id: str, title: str, **extra) -> dict:
    item = {
        "item_id": item_id,
        "title": title,
        "description": f"Deliver {title}",
        "rationale": f"Needed for {title}",
        "effort": "S",
        "depends_on": [],
        "acceptance_outcomes": [f"{title} works"],
    }
    item.update(extra)
    return item


def test_preview_add_is_read_only_and_reports_schedule_and_dag_effects(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [
        _item("ri-01", status="completed", priority=1, change_id="existing-one"),
        _item("ri-02", priority=2, depends_on=["ri-01"], change_id="existing-two"),
    ])
    before = roadmap_path.read_bytes()

    preview = preview_refinement(
        roadmap_path,
        _request({
            "op": "add",
            "after": "ri-02",
            "item": _new_item("ri-03", "New capability", depends_on=["ri-02"]),
        }),
        repo_root,
    )

    assert preview.errors == []
    assert preview.new_item_ids == ["ri-03"]
    assert preview.scaffold_change_ids == ["new-capability"]
    assert preview.schedule_before == [["ri-02"]]
    assert preview.schedule_after == [["ri-02"], ["ri-03"]]
    assert ("active:ri-03", "active:ri-02") in preview.dependency_edges_added
    assert roadmap_path.read_bytes() == before
    assert not (repo_root / "openspec" / "changes" / "new-capability").exists()


def test_edit_preserves_lifecycle_fields_and_completed_status(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [{
        **_item("ri-01", status="completed", change_id="done-change"),
        "learning_refs": ["learnings/ri-01.md"],
    }])

    preview = preview_refinement(
        roadmap_path,
        _request({
            "op": "edit",
            "item_id": "ri-01",
            "set": {"description": "Clarify the delivered behavior."},
        }),
        repo_root,
    )

    item = preview.candidate["items"][0]
    assert preview.errors == []
    assert item["status"] == "completed"
    assert item["change_id"] == "done-change"
    assert item["learning_refs"] == ["learnings/ri-01.md"]


@pytest.mark.parametrize("protected", ["status", "change_id", "item_id", "learning_refs"])
def test_edit_rejects_protected_lifecycle_fields(repo_root: Path, protected: str):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01", status="completed")])
    preview = preview_refinement(
        roadmap_path,
        _request({"op": "edit", "item_id": "ri-01", "set": {protected: "changed"}}),
        repo_root,
    )
    assert any("protected" in error and protected in error for error in preview.errors)


def test_split_supersedes_original_and_rewires_downstream_dependencies(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [
        _item("ri-01", status="completed", priority=1),
        _item("ri-02", priority=2, depends_on=["ri-01"]),
        _item("ri-03", priority=3, depends_on=["ri-02"]),
    ])
    preview = preview_refinement(
        roadmap_path,
        _request({
            "op": "split",
            "item_id": "ri-02",
            "strategy": "chain",
            "items": [
                _new_item("ri-04", "First half"),
                _new_item("ri-05", "Second half"),
            ],
        }),
        repo_root,
    )

    by_id = {item["item_id"]: item for item in preview.candidate["items"]}
    assert preview.errors == []
    assert by_id["ri-02"]["status"] == "superseded"
    assert by_id["ri-02"]["superseded_by"] == ["active:ri-04", "active:ri-05"]
    assert by_id["ri-04"]["depends_on"] == ["ri-01"]
    assert by_id["ri-05"]["depends_on"] == ["ri-04"]
    assert by_id["ri-03"]["depends_on"] == ["ri-05"]
    assert preview.new_item_ids == ["ri-04", "ri-05"]


def test_split_rejects_item_referenced_by_checkpoint(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01")])
    checkpoint = roadmap_path.parent / "checkpoint.json"
    checkpoint.write_text(json.dumps({
        "schema_version": 1,
        "roadmap_id": "active",
        "current_item_id": "ri-01",
        "phase": "implementing",
        "created_at": "2026-08-27T00:00:00Z",
        "completed_items": [],
        "failed_items": [],
    }))

    preview = preview_refinement(
        roadmap_path,
        _request({
            "op": "split",
            "item_id": "ri-01",
            "items": [_new_item("ri-02", "Replacement")],
        }),
        repo_root,
    )

    assert any("checkpoint" in error and "ri-01" in error for error in preview.errors)


def test_reorder_moves_one_item_and_renumbers_priorities(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [
        _item("ri-01", priority=1),
        _item("ri-02", priority=2),
        _item("ri-03", priority=3),
    ])
    preview = preview_refinement(
        roadmap_path,
        _request({"op": "reorder", "item_id": "ri-03", "before": "ri-01"}),
        repo_root,
    )

    assert preview.errors == []
    assert [item["item_id"] for item in preview.candidate["items"]] == [
        "ri-03", "ri-01", "ri-02",
    ]
    assert [item["priority"] for item in preview.candidate["items"]] == [1, 2, 3]


def test_supersede_rewires_dependents_to_cross_roadmap_successor(repo_root: Path):
    _write_roadmap(repo_root, [_item("ri-99", status="approved")], roadmap_id="successor")
    roadmap_path = _write_roadmap(repo_root, [
        _item("ri-01", priority=1),
        _item("ri-02", priority=2, depends_on=["ri-01"]),
    ])

    preview = preview_refinement(
        roadmap_path,
        _request({"op": "supersede", "item_id": "ri-01", "by": ["successor:ri-99"]}),
        repo_root,
    )

    by_id = {item["item_id"]: item for item in preview.candidate["items"]}
    assert preview.errors == []
    assert by_id["ri-01"]["status"] == "superseded"
    assert by_id["ri-01"]["superseded_by"] == ["successor:ri-99"]
    assert by_id["ri-02"]["depends_on"] == []
    assert by_id["ri-02"]["external_depends_on"] == ["successor:ri-99"]


@pytest.mark.parametrize("state", ["active", "archived"])
def test_preview_rejects_new_change_id_that_already_exists(repo_root: Path, state: str):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01", status="completed")])
    if state == "active":
        collision = repo_root / "openspec" / "changes" / "duplicate-change"
    else:
        collision = repo_root / "openspec" / "changes" / "archive" / "2026-01-01-duplicate-change"
    collision.mkdir(parents=True)

    preview = preview_refinement(
        roadmap_path,
        _request({
            "op": "add",
            "item": _new_item("ri-02", "Duplicate", change_id="duplicate-change"),
        }),
        repo_root,
    )

    assert any("duplicate-change" in error and state in error for error in preview.errors)


def test_apply_scaffolds_only_new_items_and_preserves_workspace_state(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [{
        **_item("ri-01", status="completed", change_id="existing-change"),
        "learning_refs": ["learnings/ri-01.md"],
    }])
    existing = repo_root / "openspec" / "changes" / "existing-change"
    existing.mkdir(parents=True)
    marker = existing / "operator-notes.md"
    marker.write_text("do not touch\n")
    checkpoint = roadmap_path.parent / "checkpoint.json"
    checkpoint.write_text('{"current_item_id":"ri-01","completed_items":["ri-01"]}\n')
    learning = roadmap_path.parent / "learnings" / "ri-01.md"
    learning.parent.mkdir()
    learning.write_text("hard-won learning\n")

    request = _request({
        "op": "add",
        "item": _new_item("ri-02", "Fresh change", depends_on=["ri-01"]),
    })
    preview = preview_refinement(roadmap_path, request, repo_root)
    observed_during_validation: list[bool] = []

    def strict_validator(root: Path) -> list[str]:
        observed_during_validation.append(
            (root / "openspec" / "changes" / "fresh-change" / "proposal.md").exists()
        )
        return []

    result = apply_refinement(
        roadmap_path,
        request,
        repo_root,
        expected_base_sha256=preview.base_sha256,
        strict_validator=strict_validator,
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
    )

    saved = yaml.safe_load(roadmap_path.read_text())
    assert result.scaffolded_change_ids == ["fresh-change"]
    assert observed_during_validation == [True]
    assert marker.read_text() == "do not touch\n"
    assert checkpoint.read_text() == '{"current_item_id":"ri-01","completed_items":["ri-01"]}\n'
    assert learning.read_text() == "hard-won learning\n"
    assert saved["items"][0]["status"] == "completed"
    assert saved["refinements"][-1] == {
        "timestamp": "2026-08-27T12:00:00+00:00",
        "actor": "codex",
        "source": "operator request",
        "rationale": "Adjust the active roadmap after new evidence.",
        "base_sha256": preview.base_sha256,
        "operations": ["add:ri-02"],
    }


def test_apply_rolls_back_roadmap_and_new_scaffolds_on_strict_validation_failure(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01", status="completed")])
    before = roadmap_path.read_bytes()
    request = _request({"op": "add", "item": _new_item("ri-02", "Will roll back")})
    preview = preview_refinement(roadmap_path, request, repo_root)

    with pytest.raises(RefinementValidationError, match="strict OpenSpec"):
        apply_refinement(
            roadmap_path,
            request,
            repo_root,
            expected_base_sha256=preview.base_sha256,
            strict_validator=lambda _root: ["strict OpenSpec failure"],
        )

    assert roadmap_path.read_bytes() == before
    assert not (repo_root / "openspec" / "changes" / "will-roll-back").exists()


def test_apply_rejects_stale_preview_base(repo_root: Path):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01")])
    request = _request({"op": "add", "item": _new_item("ri-02", "Later")})
    preview = preview_refinement(roadmap_path, request, repo_root)
    roadmap_path.write_text(roadmap_path.read_text() + "# operator edit\n")

    with pytest.raises(BaseRoadmapChangedError):
        apply_refinement(
            roadmap_path,
            request,
            repo_root,
            expected_base_sha256=preview.base_sha256,
            strict_validator=lambda _root: [],
        )


def test_preview_rejects_archived_roadmap_workspace(repo_root: Path):
    active = _write_roadmap(repo_root, [_item("ri-01")])
    archived = repo_root / "openspec" / "roadmaps" / "archive" / "2026-08-27-active"
    archived.mkdir(parents=True)
    roadmap_path = archived / "roadmap.yaml"
    roadmap_path.write_bytes(active.read_bytes())

    preview = preview_refinement(
        roadmap_path,
        _request({"op": "edit", "item_id": "ri-01", "set": {"effort": "S"}}),
        repo_root,
    )

    assert any("archived roadmap" in error.lower() for error in preview.errors)


def test_apply_removes_partial_scaffold_when_scaffolder_raises(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch,
):
    roadmap_path = _write_roadmap(repo_root, [_item("ri-01", status="completed")])
    before = roadmap_path.read_bytes()
    request = _request({"op": "add", "item": _new_item("ri-02", "Partial scaffold")})
    preview = preview_refinement(roadmap_path, request, repo_root)

    def partial_scaffold(roadmap, root, item_id):
        destination = root / "openspec" / "changes" / roadmap.get_item(item_id).change_id
        destination.mkdir(parents=True)
        (destination / "proposal.md").write_text("partial\n")
        raise OSError("disk full")

    monkeypatch.setattr("refiner.scaffold_change", partial_scaffold)

    with pytest.raises(OSError, match="disk full"):
        apply_refinement(
            roadmap_path,
            request,
            repo_root,
            expected_base_sha256=preview.base_sha256,
            strict_validator=lambda _root: [],
        )

    assert roadmap_path.read_bytes() == before
    assert not (repo_root / "openspec" / "changes" / "partial-scaffold").exists()


def test_refinement_provenance_survives_runtime_round_trip_and_schema_validation(
    repo_root: Path,
):
    data = yaml.safe_load(_write_roadmap(repo_root, [_item("ri-01")]).read_text())
    data["refinements"] = [{
        "timestamp": "2026-08-27T12:00:00+00:00",
        "actor": "codex",
        "source": "operator request",
        "rationale": "Respond to evidence.",
        "base_sha256": "a" * 64,
        "operations": ["edit:ri-01"],
    }]

    assert validate_against_schema(data, "openspec/schemas/roadmap.schema.json", repo_root) == []
    assert Roadmap.from_dict(data).to_dict()["refinements"] == data["refinements"]
