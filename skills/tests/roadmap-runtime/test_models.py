"""Tests for roadmap artifact models and serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# Ensure the scripts directory is importable
from models import (
    Checkpoint,
    CheckpointPhase,
    Effort,
    ItemStatus,
    LearningDecision,
    LearningEntry,
    LearningPhase,
    Policy,
    PolicyAction,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    load_roadmap,
    save_roadmap,
)


def _make_item(item_id: str = "ri-01", **kwargs) -> RoadmapItem:
    defaults = {
        "title": "Test item",
        "status": ItemStatus.APPROVED,
        "priority": 1,
        "effort": Effort.M,
        "depends_on": [],
    }
    defaults.update(kwargs)
    return RoadmapItem(item_id=item_id, **defaults)

def _make_roadmap(**kwargs) -> Roadmap:
    defaults = {
        "schema_version": 1,
        "roadmap_id": "test-roadmap",
        "source_proposal": "proposals/test.md",
        "items": [_make_item()],
    }
    defaults.update(kwargs)
    return Roadmap(**defaults)

class TestRoadmapItem:
    def test_round_trip(self):
        item = _make_item(description="A test", acceptance_outcomes=["tests pass"])
        d = item.to_dict()
        restored = RoadmapItem.from_dict(d)
        assert restored.item_id == item.item_id
        assert restored.status == item.status
        assert restored.effort == item.effort
        assert restored.acceptance_outcomes == ["tests pass"]

    def test_optional_fields_omitted(self):
        item = _make_item()
        d = item.to_dict()
        assert "description" not in d
        assert "failure_reason" not in d

    def test_failure_fields(self):
        item = _make_item(
            status=ItemStatus.FAILED,
            failure_reason="Tests did not pass",
            blocked_by=["ri-02"],
        )
        d = item.to_dict()
        assert d["failure_reason"] == "Tests did not pass"
        assert d["blocked_by"] == ["ri-02"]

class TestRoadmap:
    def test_round_trip(self):
        roadmap = _make_roadmap()
        d = roadmap.to_dict()
        restored = Roadmap.from_dict(d)
        assert restored.roadmap_id == roadmap.roadmap_id
        assert len(restored.items) == 1
        assert restored.policy.default_action == PolicyAction.WAIT

    def test_get_item(self):
        roadmap = _make_roadmap()
        assert roadmap.get_item("ri-01") is not None
        assert roadmap.get_item("nonexistent") is None

    def test_ready_items_no_deps(self):
        roadmap = _make_roadmap(items=[
            _make_item("ri-01", status=ItemStatus.APPROVED),
            _make_item("ri-02", status=ItemStatus.APPROVED),
        ])
        ready = roadmap.ready_items()
        assert len(ready) == 2

    def test_ready_items_with_deps(self):
        roadmap = _make_roadmap(items=[
            _make_item("ri-01", status=ItemStatus.COMPLETED),
            _make_item("ri-02", status=ItemStatus.APPROVED, depends_on=["ri-01"]),
            _make_item("ri-03", status=ItemStatus.APPROVED, depends_on=["ri-02"]),
        ])
        ready = roadmap.ready_items()
        assert len(ready) == 1
        assert ready[0].item_id == "ri-02"

    def test_ready_items_blocked_dep(self):
        roadmap = _make_roadmap(items=[
            _make_item("ri-01", status=ItemStatus.FAILED),
            _make_item("ri-02", status=ItemStatus.APPROVED, depends_on=["ri-01"]),
        ])
        ready = roadmap.ready_items()
        assert len(ready) == 0

    def test_no_cycle(self):
        roadmap = _make_roadmap(items=[
            _make_item("ri-01"),
            _make_item("ri-02", depends_on=["ri-01"]),
        ])
        assert not roadmap.has_cycle()

    def test_cycle_detected(self):
        roadmap = _make_roadmap(items=[
            _make_item("ri-01", depends_on=["ri-02"]),
            _make_item("ri-02", depends_on=["ri-01"]),
        ])
        assert roadmap.has_cycle()

    def test_save_load_yaml(self, tmp_path):
        roadmap = _make_roadmap()
        path = tmp_path / "roadmap.yaml"
        save_roadmap(roadmap, path)

        content = path.read_text()
        data = yaml.safe_load(content)
        assert data["roadmap_id"] == "test-roadmap"
        assert data["updated_at"] is not None

        # Load back without schema validation (no repo_root)
        loaded = load_roadmap(path)
        assert loaded.roadmap_id == roadmap.roadmap_id

class TestPolicy:
    def test_defaults(self):
        policy = Policy()
        assert policy.default_action == PolicyAction.WAIT
        assert policy.max_switch_attempts_per_item == 2

    def test_round_trip(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            cost_ceiling_usd=5.0,
            preferred_vendor="claude",
        )
        d = policy.to_dict()
        restored = Policy.from_dict(d)
        assert restored.default_action == PolicyAction.SWITCH
        assert restored.cost_ceiling_usd == 5.0

class TestCheckpoint:
    def test_create(self):
        cp = Checkpoint.create("test-roadmap", "ri-01")
        assert cp.current_item_id == "ri-01"
        assert cp.phase == CheckpointPhase.PLANNING
        assert cp.created_at is not None

    def test_round_trip(self, tmp_path):
        cp = Checkpoint.create("test-roadmap", "ri-01")
        cp.completed_items = ["ri-00"]

        path = tmp_path / "checkpoint.json"
        path.write_text(json.dumps(cp.to_dict(), indent=2))
        loaded = Checkpoint.from_dict(json.loads(path.read_text()))
        assert loaded.completed_items == ["ri-00"]

class TestLearningEntry:
    def test_to_dict(self):
        entry = LearningEntry(
            schema_version=1,
            item_id="ri-01",
            timestamp="2026-04-13T00:00:00Z",
            decisions=[LearningDecision(title="Use REST", outcome="Selected REST over GraphQL")],
            phase=LearningPhase.IMPLEMENTATION,
            recommendations=["Consider caching for ri-02"],
        )
        d = entry.to_dict()
        assert d["item_id"] == "ri-01"
        assert len(d["decisions"]) == 1
        assert d["recommendations"] == ["Consider caching for ri-02"]
