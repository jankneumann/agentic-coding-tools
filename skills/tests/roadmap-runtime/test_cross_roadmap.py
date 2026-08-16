"""Tests for typed cross-roadmap edges in the roadmap-runtime models.

Covers the model round-trip of ``external_depends_on`` / ``superseded_by`` and
the ``superseded`` status, the read-only sibling-roadmap loaders, and the
readiness rules: an external prerequisite is satisfied when the referenced item
reaches ``completed`` (auto-becomes-ready, no manual status edit), and
``superseded`` items are never ready.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from models import (
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    completed_external_refs,
    external_item_status,
    is_valid_item_ref,
    load_all_roadmaps,
    parse_item_ref,
)


def _item(item_id: str, **kwargs) -> RoadmapItem:
    defaults: dict = {
        "title": "Item",
        "status": ItemStatus.APPROVED,
        "priority": 1,
        "effort": Effort.M,
    }
    defaults.update(kwargs)
    return RoadmapItem(item_id=item_id, **defaults)


def _write_roadmap(repo_root: Path, roadmap_id: str, items: list[RoadmapItem]) -> None:
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=roadmap_id,
        source_proposal=f"openspec/roadmaps/{roadmap_id}/proposal.md",
        items=items,
        status=RoadmapStatus.APPROVED,
    )
    path = repo_root / "openspec" / "roadmaps" / roadmap_id / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False))


# ---------------------------------------------------------------------------
# item_ref grammar
# ---------------------------------------------------------------------------
class TestItemRef:
    def test_parse_valid(self):
        assert parse_item_ref("symphony:ri-04") == ("symphony", "ri-04")

    def test_is_valid(self):
        assert is_valid_item_ref("a:b")
        assert not is_valid_item_ref("no-colon")
        assert not is_valid_item_ref("a:b:c")
        assert not is_valid_item_ref(":b")
        assert not is_valid_item_ref("a:")


# ---------------------------------------------------------------------------
# Model round-trip
# ---------------------------------------------------------------------------
class TestModelRoundTrip:
    def test_external_edges_round_trip(self):
        item = _item(
            "ri-01",
            external_depends_on=["other:ri-09"],
            superseded_by=["symphony:ri-02"],
            acceptance_outcomes=["done"],
        )
        d = item.to_dict()
        assert d["external_depends_on"] == ["other:ri-09"]
        assert d["superseded_by"] == ["symphony:ri-02"]
        restored = RoadmapItem.from_dict(d)
        assert restored.external_depends_on == ["other:ri-09"]
        assert restored.superseded_by == ["symphony:ri-02"]

    def test_empty_edges_omitted(self):
        d = _item("ri-01").to_dict()
        assert "external_depends_on" not in d
        assert "superseded_by" not in d

    def test_superseded_status_round_trips(self):
        item = _item("ri-01", status=ItemStatus.SUPERSEDED)
        restored = RoadmapItem.from_dict(item.to_dict())
        assert restored.status == ItemStatus.SUPERSEDED

    def test_legacy_item_without_edges_loads(self):
        # Backward compatibility: an item mapping with no external fields loads
        # to empty lists, not errors.
        legacy = {
            "item_id": "ri-01",
            "title": "Legacy",
            "status": "approved",
            "priority": 1,
            "effort": "M",
            "depends_on": [],
        }
        item = RoadmapItem.from_dict(legacy)
        assert item.external_depends_on == []
        assert item.superseded_by == []


# ---------------------------------------------------------------------------
# Sibling loaders
# ---------------------------------------------------------------------------
class TestSiblingLoaders:
    def test_load_all_roadmaps_keys_by_roadmap_id(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01", acceptance_outcomes=["x"])])
        _write_roadmap(tmp_path, "beta", [_item("ri-01", acceptance_outcomes=["x"])])
        loaded = load_all_roadmaps(tmp_path)
        assert set(loaded) == {"alpha", "beta"}

    def test_external_item_status_and_completed_refs(self, tmp_path):
        _write_roadmap(
            tmp_path,
            "alpha",
            [
                _item("ri-01", status=ItemStatus.COMPLETED, acceptance_outcomes=["x"]),
                _item("ri-02", status=ItemStatus.APPROVED, acceptance_outcomes=["x"]),
            ],
        )
        status = external_item_status(tmp_path)
        assert status["alpha:ri-01"] == "completed"
        assert status["alpha:ri-02"] == "approved"
        assert completed_external_refs(tmp_path) == {"alpha:ri-01"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert load_all_roadmaps(tmp_path) == {}
        assert completed_external_refs(tmp_path) == set()


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
class TestReadiness:
    def test_external_dep_blocks_until_completed(self):
        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="beta",
            source_proposal="p.md",
            items=[
                _item(
                    "ri-01",
                    status=ItemStatus.APPROVED,
                    external_depends_on=["alpha:ri-09"],
                    acceptance_outcomes=["x"],
                ),
            ],
        )
        # External prerequisite not yet completed -> not ready.
        assert roadmap.ready_items(external_completed=set()) == []
        # NO manual status edit — same APPROVED item becomes ready once the
        # external prerequisite is reported completed.
        ready = roadmap.ready_items(external_completed={"alpha:ri-09"})
        assert [i.item_id for i in ready] == ["ri-01"]

    def test_superseded_items_never_ready(self):
        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="beta",
            source_proposal="p.md",
            items=[
                _item(
                    "ri-01",
                    status=ItemStatus.SUPERSEDED,
                    superseded_by=["alpha:ri-02"],
                    acceptance_outcomes=["x"],
                ),
            ],
        )
        assert roadmap.ready_items(external_completed={"alpha:ri-02"}) == []

    def test_auto_ready_when_external_prereq_marked_completed(self, tmp_path):
        # (d) End-to-end via the file-backed helper: an item blocked only by an
        # external prerequisite auto-becomes-ready when that prerequisite is
        # marked completed in its own roadmap — with NO edit to the dependent.
        _write_roadmap(
            tmp_path,
            "alpha",
            [_item("ri-09", status=ItemStatus.APPROVED, acceptance_outcomes=["x"])],
        )
        beta = Roadmap(
            schema_version=1,
            roadmap_id="beta",
            source_proposal="p.md",
            items=[
                _item(
                    "ri-01",
                    status=ItemStatus.APPROVED,
                    external_depends_on=["alpha:ri-09"],
                    acceptance_outcomes=["x"],
                ),
            ],
        )

        # Before: alpha:ri-09 is only approved -> beta:ri-01 withheld.
        assert beta.ready_items(completed_external_refs(tmp_path)) == []

        # Mark the external prerequisite completed in alpha (its own roadmap).
        _write_roadmap(
            tmp_path,
            "alpha",
            [_item("ri-09", status=ItemStatus.COMPLETED, acceptance_outcomes=["x"])],
        )

        ready = beta.ready_items(completed_external_refs(tmp_path))
        assert [i.item_id for i in ready] == ["ri-01"]
