"""Approval routing from a candidate stub into a refiner request."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills/supervise/scripts"
REFINER_SCRIPTS = REPO_ROOT / "skills/refine-roadmap/scripts"
SCHEMAS = REPO_ROOT / "openspec/schemas"
for scripts_dir in (SCRIPTS, REFINER_SCRIPTS):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from digest import build_status_index, store_candidates, stub_to_request  # noqa: E402
from refiner import (  # noqa: E402
    BaseRoadmapChangedError,
    apply_refinement,
    preview_refinement,
)


def _item(item_id: str, *, status: str, change_id: str | None = None) -> dict:
    item = {
        "item_id": item_id,
        "title": item_id,
        "status": status,
        "priority": 1,
        "effort": "S",
        "depends_on": [],
        "acceptance_outcomes": ["done"],
    }
    if change_id:
        item["change_id"] = change_id
    return item


def _roadmap(repo: Path, roadmap_id: str, items: list[dict]) -> Path:
    path = repo / f"openspec/roadmaps/{roadmap_id}/roadmap.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id,
                "source_proposal": f"docs/proposals/{roadmap_id}.md",
                "status": "planning",
                "items": items,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _stub(*, dependencies: list[str] | None = None, change_id: str = "add-routed-work") -> dict:
    return {
        "schema_version": 1,
        "title": "Routed work",
        "description": "Implement the routed capability.",
        "rationale": "It closes a verified gap.",
        "provenance": {
            "source_artifact": "reports/gap.md",
            "finding_ids": ["F-7", "F-8"],
            "generator": "bug-scrub",
        },
        "effort": "M",
        "priority": 7,
        "suggested_change_id": change_id,
        "depends_on": dependencies or [],
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    schemas = root / "openspec/schemas"
    schemas.mkdir(parents=True)
    for name in (
        "candidate-work.schema.json",
        "supervise-digest.schema.json",
        "supervise-rubric-score.schema.json",
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
        "roadmap.schema.json",
    ):
        shutil.copy2(SCHEMAS / name, schemas / name)
    return root


def test_status_index_distinguishes_completed_blocked_pending_and_archived(repo: Path) -> None:
    _roadmap(
        repo,
        "target",
        [
            _item("ri-01", status="completed", change_id="add-complete"),
            _item("ri-02", status="blocked", change_id="add-blocked"),
            _item("ri-03", status="approved", change_id="add-pending"),
        ],
    )
    archived = repo / "openspec/changes/archive/2026-09-01-add-archived"
    archived.mkdir(parents=True)
    (archived / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    active = repo / "openspec/changes/add-active"
    active.mkdir(parents=True)
    (active / "tasks.md").write_text("- [x] implemented but not archived\n", encoding="utf-8")

    index = build_status_index(repo)

    assert index.resolve("add-complete").completed is True
    assert index.resolve("target:ri-01").completed is True
    assert index.resolve("add-blocked").status == "blocked"
    assert index.resolve("add-pending").completed is False
    assert index.resolve("add-archived").completed is True
    assert index.resolve("add-active").status == "pending-stub"
    assert index.resolve("add-active").completed is False
    assert index.resolve("add-missing").status == "unresolved"


def test_stub_to_request_maps_fields_next_id_position_and_dependency_types(repo: Path) -> None:
    target = _roadmap(
        repo,
        "target",
        [
            _item("ri-01", status="completed", change_id="add-local"),
            _item("ri-08", status="approved", change_id="add-existing"),
        ],
    )
    _roadmap(repo, "other", [_item("ri-04", status="completed", change_id="add-cross")])
    archived = repo / "openspec/changes/archive/2026-09-01-add-archived"
    archived.mkdir(parents=True)
    (archived / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    stub = _stub(dependencies=["add-local", "other:ri-04", "add-archived"])
    store_candidates(repo, [stub], record=None, as_of="2026-09-11T01:00:00Z")
    before = target.read_bytes()

    request = stub_to_request(
        repo,
        "change:add-routed-work",
        roadmap_id="target",
        acceptance=["First outcome", "Second outcome"],
        after="ri-01",
    )

    assert list(request) == ["rationale", "actor", "source", "operations"]
    assert request["rationale"] == stub["rationale"]
    assert request["actor"] == "supervise"
    assert request["source"] == "candidate-digest:change:add-routed-work"
    assert len(request["operations"]) == 1
    operation = request["operations"][0]
    assert operation["op"] == "add"
    assert operation["after"] == "ri-01"
    assert operation["item"] == {
        "item_id": "ri-09",
        "title": "Routed work",
        "description": "Implement the routed capability.\n\nProvenance: reports/gap.md (F-7, F-8)",
        "rationale": "It closes a verified gap.",
        "effort": "M",
        "priority": 7,
        "status": "approved",
        "change_id": "add-routed-work",
        "depends_on": ["ri-01"],
        "external_depends_on": ["other:ri-04"],
        "acceptance_outcomes": ["First outcome", "Second outcome"],
    }
    assert target.read_bytes() == before


def test_stub_to_request_appends_by_default_without_changing_priority(repo: Path) -> None:
    _roadmap(repo, "target", [_item("ri-03", status="approved")])
    store_candidates(repo, [_stub()], record=None, as_of="2026-09-11T01:00:00Z")

    request = stub_to_request(
        repo, "change:add-routed-work", roadmap_id="target", acceptance=["done"]
    )

    assert "after" not in request["operations"][0]
    assert request["operations"][0]["item"]["priority"] == 7


@pytest.mark.parametrize("acceptance", [[], [""]])
def test_stub_to_request_requires_nonempty_acceptance(repo: Path, acceptance: list[str]) -> None:
    _roadmap(repo, "target", [])
    store_candidates(repo, [_stub()], record=None, as_of="2026-09-11T01:00:00Z")
    with pytest.raises(ValueError, match="acceptance outcome"):
        stub_to_request(
            repo, "change:add-routed-work", roadmap_id="target", acceptance=acceptance
        )


def test_stub_to_request_refuses_unresolved_dependency(repo: Path) -> None:
    _roadmap(repo, "target", [])
    store_candidates(
        repo, [_stub(dependencies=["add-does-not-exist"])], record=None, as_of="2026-09-11T01:00:00Z"
    )
    with pytest.raises(ValueError, match="add-does-not-exist"):
        stub_to_request(
            repo, "change:add-routed-work", roadmap_id="target", acceptance=["done"]
        )


def test_stub_to_request_refuses_change_id_collision(repo: Path) -> None:
    _roadmap(repo, "target", [_item("ri-01", status="approved", change_id="add-routed-work")])
    store_candidates(repo, [_stub()], record=None, as_of="2026-09-11T01:00:00Z")
    with pytest.raises(ValueError, match="collision"):
        stub_to_request(
            repo, "change:add-routed-work", roadmap_id="target", acceptance=["done"]
        )


def test_stub_request_runs_real_refiner_preview_apply_and_stale_sha_refusal(repo: Path) -> None:
    target = _roadmap(repo, "target", [_item("ri-01", status="completed", change_id="add-done")])
    stub = _stub()
    store_candidates(repo, [stub], record=None, as_of="2026-09-11T01:00:00Z")
    request = stub_to_request(
        repo,
        "change:add-routed-work",
        roadmap_id="target",
        acceptance=["Roadmap transaction completes"],
    )

    preview = preview_refinement(target, request, repo)
    assert preview.errors == []
    result = apply_refinement(
        target,
        request,
        repo,
        expected_base_sha256=preview.base_sha256,
        strict_validator=lambda _root: [],
    )

    assert result.scaffolded_change_ids == ["add-routed-work"]
    assert (repo / "openspec/changes/add-routed-work/proposal.md").is_file()
    with pytest.raises(BaseRoadmapChangedError, match="changed after preview"):
        apply_refinement(
            target,
            request,
            repo,
            expected_base_sha256=preview.base_sha256,
            strict_validator=lambda _root: [],
        )
