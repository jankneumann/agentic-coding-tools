"""Tests for bounded context assembly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from context import assemble_context, assemble_summary
from learning import write_entry
from models import (
    Checkpoint,
    CheckpointPhase,
    Effort,
    ItemStatus,
    LearningDecision,
    LearningEntry,
    LearningPhase,
    Roadmap,
    RoadmapItem,
    save_checkpoint,
    save_roadmap,
)


def _setup_workspace(tmp_path: Path) -> None:
    """Create a minimal workspace with roadmap, checkpoint, and learning entries."""
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="test",
        source_proposal="test.md",
        items=[
            RoadmapItem("ri-01", "First", ItemStatus.COMPLETED, 1, Effort.S),
            RoadmapItem("ri-02", "Second", ItemStatus.IN_PROGRESS, 2, Effort.M, depends_on=["ri-01"]),
            RoadmapItem("ri-03", "Third", ItemStatus.APPROVED, 3, Effort.M, depends_on=["ri-02"]),
        ],
    )
    save_roadmap(roadmap, tmp_path / "roadmap.yaml")

    checkpoint = Checkpoint(
        schema_version=1,
        roadmap_id="test",
        current_item_id="ri-02",
        phase=CheckpointPhase.IMPLEMENTING,
        created_at="2026-04-13T00:00:00Z",
        completed_items=["ri-01"],
    )
    save_checkpoint(checkpoint, tmp_path / "checkpoint.json")

    write_entry(tmp_path, LearningEntry(
        schema_version=1,
        item_id="ri-01",
        timestamp="2026-04-13T00:00:00Z",
        decisions=[LearningDecision("Decision", "Used approach X")],
        phase=LearningPhase.IMPLEMENTATION,
    ))

class TestAssembleContext:
    def test_loads_context(self, tmp_path):
        _setup_workspace(tmp_path)
        ctx = assemble_context(tmp_path)
        assert ctx.item_id == "ri-02"
        assert ctx.roadmap.roadmap_id == "test"
        assert ctx.checkpoint.phase == CheckpointPhase.IMPLEMENTING

    def test_loads_dependency_learnings(self, tmp_path):
        _setup_workspace(tmp_path)
        ctx = assemble_context(tmp_path)
        assert len(ctx.learning_entries) >= 1
        assert len(ctx.dependency_learnings) >= 1

    def test_missing_item_raises(self, tmp_path):
        _setup_workspace(tmp_path)
        # Corrupt checkpoint to reference nonexistent item
        cp = json.loads((tmp_path / "checkpoint.json").read_text())
        cp["current_item_id"] = "nonexistent"
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp))

        with pytest.raises(ValueError, match="not found in roadmap"):
            assemble_context(tmp_path)

class TestAssembleSummary:
    def test_produces_summary(self, tmp_path):
        _setup_workspace(tmp_path)
        summary = assemble_summary(tmp_path)
        assert summary["roadmap_id"] == "test"
        assert summary["total_items"] == 3
        assert summary["current_item"] == "ri-02"
        assert summary["completed_count"] == 1
