"""Tests for checkpoint manager."""

from __future__ import annotations

from pathlib import Path

import pytest
from checkpoint import CheckpointManager
from models import (
    Checkpoint,
    CheckpointPhase,
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)


def _make_roadmap(items: list[RoadmapItem] | None = None) -> Roadmap:
    if items is None:
        items = [
            RoadmapItem("ri-01", "First", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Second", ItemStatus.APPROVED, 2, Effort.M, depends_on=["ri-01"]),
            RoadmapItem("ri-03", "Third", ItemStatus.APPROVED, 3, Effort.M, depends_on=["ri-02"]),
        ]
    return Roadmap(
        schema_version=1,
        roadmap_id="test",
        source_proposal="test.md",
        items=items,
    )

class TestCheckpointManager:
    def test_create_and_load(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)
        assert cp.current_item_id == "ri-01"

        loaded = mgr.load()
        assert loaded.current_item_id == "ri-01"

    def test_exists(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        assert not mgr.exists()
        mgr.create(_make_roadmap())
        assert mgr.exists()

    def test_advance_phase(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())
        mgr.advance_phase(cp, CheckpointPhase.IMPLEMENTING)
        loaded = mgr.load()
        assert loaded.phase == CheckpointPhase.IMPLEMENTING

    def test_complete_item(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())
        mgr.complete_item(cp, "ri-01")
        loaded = mgr.load()
        assert "ri-01" in loaded.completed_items

    def test_complete_item_idempotent(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())
        mgr.complete_item(cp, "ri-01")
        mgr.complete_item(cp, "ri-01")
        loaded = mgr.load()
        assert loaded.completed_items.count("ri-01") == 1

    def test_fail_item(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)
        mgr.fail_item(cp, "ri-01", "Tests failed", roadmap)

        assert roadmap.get_item("ri-01").status == ItemStatus.FAILED
        assert roadmap.get_item("ri-02").status == ItemStatus.BLOCKED
        assert "ri-01" in roadmap.get_item("ri-02").blocked_by

        loaded = mgr.load()
        assert len(loaded.failed_items) == 1
        assert loaded.failed_items[0].reason == "Tests failed"

    def test_fail_item_retry_increments(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)
        mgr.fail_item(cp, "ri-01", "First attempt", roadmap)
        mgr.fail_item(cp, "ri-01", "Second attempt", roadmap)

        loaded = mgr.load()
        assert loaded.failed_items[0].retry_count == 1

    def test_advance_to_next(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)

        roadmap.get_item("ri-01").status = ItemStatus.COMPLETED
        next_id = mgr.advance_to_next(cp, roadmap)
        assert next_id == "ri-02"

    def test_advance_to_next_none(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)
        # No items completed, ri-01 is the only ready one but it's already current
        # Mark ri-01 as in_progress so ready_items returns empty
        roadmap.get_item("ri-01").status = ItemStatus.IN_PROGRESS
        next_id = mgr.advance_to_next(cp, roadmap)
        assert next_id is None

    def test_is_resumable(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())
        assert mgr.is_resumable(cp)

        cp.phase = CheckpointPhase.BLOCKED
        assert not mgr.is_resumable(cp)

    def test_should_skip_phase(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())
        cp.phase = CheckpointPhase.REVIEWING

        assert mgr.should_skip_phase(cp, "ri-01", CheckpointPhase.PLANNING)
        assert mgr.should_skip_phase(cp, "ri-01", CheckpointPhase.IMPLEMENTING)
        assert not mgr.should_skip_phase(cp, "ri-01", CheckpointPhase.REVIEWING)
        assert not mgr.should_skip_phase(cp, "ri-01", CheckpointPhase.VALIDATING)

    def test_load_nonexistent_raises(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.load()
