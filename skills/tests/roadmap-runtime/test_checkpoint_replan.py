"""Tests for the explicit replan signal on ``CheckpointManager.fail_item``.

Covers roadmap-orchestration scenarios *Explicit replan signal produces
replan_required* and the default half of *Handle individual roadmap item
implementation failure* (dependents go to ``blocked`` unless the failing
item's outcome payload said otherwise), plus the ``gate_decisions`` sidecar
the orchestrator persists on the checkpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

from checkpoint import CheckpointManager
from models import (
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_roadmap(items: list[RoadmapItem] | None = None) -> Roadmap:
    if items is None:
        items = [
            RoadmapItem("ri-01", "First", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem(
                "ri-02", "Approved dependent", ItemStatus.APPROVED, 2, Effort.M,
                depends_on=["ri-01"],
            ),
            RoadmapItem(
                "ri-03", "Candidate dependent", ItemStatus.CANDIDATE, 3, Effort.M,
                depends_on=["ri-01"],
            ),
            RoadmapItem(
                "ri-04", "Completed dependent", ItemStatus.COMPLETED, 4, Effort.S,
                depends_on=["ri-01"],
            ),
            RoadmapItem("ri-05", "Unrelated", ItemStatus.APPROVED, 5, Effort.S),
        ]
    return Roadmap(
        schema_version=1,
        roadmap_id="test",
        source_proposal="test.md",
        items=items,
    )


class TestFailItemReplanSignal:
    def test_default_keeps_blocked_behaviour(self, tmp_path):
        """Rule 4 safe default: no signal == today's exact behaviour."""
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)

        mgr.fail_item(cp, "ri-01", "Tests failed", roadmap)

        assert roadmap.get_item("ri-01").status == ItemStatus.FAILED
        assert roadmap.get_item("ri-02").status == ItemStatus.BLOCKED
        assert roadmap.get_item("ri-03").status == ItemStatus.BLOCKED
        assert all(
            item.status != ItemStatus.REPLAN_REQUIRED for item in roadmap.items
        )

    def test_replan_true_parks_dependents_in_replan_required(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)

        mgr.fail_item(cp, "ri-01", "Design dead-end", roadmap, replan=True)

        assert roadmap.get_item("ri-02").status == ItemStatus.REPLAN_REQUIRED
        assert roadmap.get_item("ri-03").status == ItemStatus.REPLAN_REQUIRED
        assert "ri-01" in roadmap.get_item("ri-02").blocked_by
        assert "ri-01" in roadmap.get_item("ri-03").blocked_by

    def test_failed_item_still_marked_failed_with_reason(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)

        mgr.fail_item(cp, "ri-01", "Design dead-end", roadmap, replan=True)

        failed = roadmap.get_item("ri-01")
        assert failed.status == ItemStatus.FAILED
        assert failed.failure_reason == "Design dead-end"
        loaded = mgr.load()
        assert [f.item_id for f in loaded.failed_items] == ["ri-01"]

    def test_completed_and_unrelated_dependents_untouched(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        roadmap = _make_roadmap()
        cp = mgr.create(roadmap)

        mgr.fail_item(cp, "ri-01", "Design dead-end", roadmap, replan=True)

        assert roadmap.get_item("ri-04").status == ItemStatus.COMPLETED
        assert roadmap.get_item("ri-04").blocked_by == []
        assert roadmap.get_item("ri-05").status == ItemStatus.APPROVED
        assert roadmap.get_item("ri-05").blocked_by == []

    def test_replan_is_keyword_only(self, tmp_path):
        """Positional order stays as-is so existing callers keep working."""
        import inspect

        sig = inspect.signature(CheckpointManager.fail_item)
        assert sig.parameters["replan"].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["replan"].default is False


class TestGateDecisionSidecar:
    def test_record_gate_decision_persists_and_reloads(self, tmp_path):
        mgr = CheckpointManager(tmp_path)
        cp = mgr.create(_make_roadmap())

        record = {
            "gate": "replan_required",
            "outcome": "blocked",
            "resolution": "posture_block",
            "disposition": "block",
            "reason": "posture blocks replan",
            "posture_present": True,
            "recorded_at": "2026-01-01T00:00:00+00:00",
        }
        mgr.record_gate_decision(cp, record)

        on_disk = json.loads((tmp_path / "checkpoint.json").read_text())
        assert on_disk["gate_decisions"] == [record]

        reloaded = mgr.load()
        assert reloaded.gate_decisions == [record]

        # Appending through the reloaded checkpoint keeps history append-only.
        mgr.record_gate_decision(reloaded, dict(record, outcome="proceed"))
        assert len(json.loads((tmp_path / "checkpoint.json").read_text())["gate_decisions"]) == 2

    def test_checkpoint_without_gate_decisions_is_unchanged(self, tmp_path):
        """No gate ever evaluated -> the key must not appear at all."""
        mgr = CheckpointManager(tmp_path)
        mgr.create(_make_roadmap())
        assert "gate_decisions" not in json.loads((tmp_path / "checkpoint.json").read_text())
        assert mgr.load().gate_decisions == []

    def test_gate_decisions_still_schema_valid(self, tmp_path):
        """checkpoint.schema.json has no additionalProperties:false, so the
        sidecar key must not break the validating load path."""
        mgr = CheckpointManager(tmp_path, _REPO_ROOT)
        cp = mgr.create(_make_roadmap())
        mgr.record_gate_decision(cp, {"gate": "replan_required", "outcome": "proceed"})
        assert mgr.load().gate_decisions[0]["gate"] == "replan_required"
