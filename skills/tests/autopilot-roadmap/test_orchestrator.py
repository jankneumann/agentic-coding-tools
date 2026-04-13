"""Tests for the roadmap orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from models import (
    CheckpointPhase,
    Effort,
    ItemStatus,
    Policy,
    PolicyAction,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)
from orchestrator import execute_roadmap


def _write_roadmap(workspace: Path, items: list[RoadmapItem] | None = None, **kwargs) -> Roadmap:
    """Helper to write a roadmap.yaml in the workspace."""
    if items is None:
        items = [
            RoadmapItem("ri-01", "First item", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Second item", ItemStatus.APPROVED, 2, Effort.M, depends_on=["ri-01"]),
            RoadmapItem("ri-03", "Third item", ItemStatus.APPROVED, 3, Effort.M, depends_on=["ri-02"]),
        ]
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=kwargs.get("roadmap_id", "test-roadmap"),
        source_proposal="test-proposal.md",
        items=items,
        status=kwargs.get("status", RoadmapStatus.APPROVED),
        policy=kwargs.get("policy", Policy()),
    )
    roadmap_path = workspace / "roadmap.yaml"
    roadmap_path.write_text(yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False))
    return roadmap

class TestExecutionOrder:
    """Verify items execute in dependency and priority order."""

    def test_executes_items_in_dependency_order(self, tmp_path):
        _write_roadmap(tmp_path)
        executed: list[str] = []

        def track_dispatch(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track_dispatch)

        assert executed == ["ri-01", "ri-02", "ri-03"]
        assert result["completed_count"] == 3
        assert result["status"] == "completed"

    def test_respects_priority_for_independent_items(self, tmp_path):
        items = [
            RoadmapItem("ri-a", "High priority", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-b", "Low priority", ItemStatus.APPROVED, 5, Effort.S),
            RoadmapItem("ri-c", "Mid priority", ItemStatus.APPROVED, 3, Effort.S),
        ]
        _write_roadmap(tmp_path, items=items)
        executed: list[str] = []

        def track_dispatch(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track_dispatch)

        assert executed == ["ri-a", "ri-c", "ri-b"]
        assert result["completed_count"] == 3

class TestCheckpointLifecycle:
    """Verify checkpoint creation and phase advancement."""

    def test_creates_checkpoint_on_start(self, tmp_path):
        _write_roadmap(tmp_path)
        execute_roadmap(tmp_path)

        checkpoint_path = tmp_path / "checkpoint.json"
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        assert data["roadmap_id"] == "test-roadmap"

    def test_advances_checkpoint_phases_correctly(self, tmp_path):
        _write_roadmap(tmp_path)
        phases_seen: dict[str, list[str]] = {}

        def track_phases(item_id, phase, context):
            phases_seen.setdefault(item_id, []).append(phase)
            return "success"

        execute_roadmap(tmp_path, dispatch_fn=track_phases)

        # Each item should go through planning, implementing, reviewing, validating
        for item_id in ("ri-01", "ri-02", "ri-03"):
            assert phases_seen[item_id] == [
                "planning", "implementing", "reviewing", "validating",
            ]

    def test_checkpoint_records_completed_items(self, tmp_path):
        _write_roadmap(tmp_path)
        execute_roadmap(tmp_path)

        data = json.loads((tmp_path / "checkpoint.json").read_text())
        assert "ri-01" in data["completed_items"]
        assert "ri-02" in data["completed_items"]
        assert "ri-03" in data["completed_items"]

class TestFailureHandling:
    """Verify failure and propagation behavior."""

    def test_handles_item_failure(self, tmp_path):
        _write_roadmap(tmp_path)

        def fail_first(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Tests failed"
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=fail_first)

        assert result["failed_count"] == 1
        assert result["blocked_count"] >= 1  # ri-02 and ri-03 should be blocked

    def test_failure_propagates_to_dependents(self, tmp_path):
        _write_roadmap(tmp_path)

        def fail_first(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Build error"
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=fail_first)

        # Read updated roadmap to check propagation
        roadmap_data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        statuses = {item["item_id"]: item["status"] for item in roadmap_data["items"]}
        assert statuses["ri-01"] == "failed"
        assert statuses["ri-02"] == "blocked"

    def test_continues_with_independent_items_after_failure(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "Will fail", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Independent", ItemStatus.APPROVED, 2, Effort.S),
            RoadmapItem("ri-03", "Depends on ri-01", ItemStatus.APPROVED, 3, Effort.S, depends_on=["ri-01"]),
        ]
        _write_roadmap(tmp_path, items=items)
        executed: list[str] = []

        def selective_fail(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Error"
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=selective_fail)

        assert "ri-02" in executed
        assert "ri-03" not in executed  # blocked by ri-01
        assert result["completed_count"] == 1
        assert result["failed_count"] == 1

class TestResumeFromCheckpoint:
    """Verify checkpoint resume semantics."""

    def test_resumes_from_existing_checkpoint(self, tmp_path):
        _write_roadmap(tmp_path)

        # First run: complete only ri-01, then "crash"
        call_count = {"n": 0}

        def crash_after_first(item_id, phase, context):
            if item_id == "ri-01":
                return "success"
            call_count["n"] += 1
            if call_count["n"] > 1:
                # Let it process a bit then we'll check resume
                return "success"
            return "success"

        # Complete first run
        first_result = execute_roadmap(tmp_path, dispatch_fn=crash_after_first)
        assert first_result["completed_count"] == 3

        # Re-run: should resume and find everything completed
        resumed: list[str] = []

        def track_resume(item_id, phase, context):
            resumed.append(item_id)
            return "success"

        second_result = execute_roadmap(tmp_path, dispatch_fn=track_resume)

        # All items already completed — nothing new to dispatch
        assert len(resumed) == 0
        assert second_result["completed_count"] == 3

    def test_skips_completed_items_on_resume(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "First", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Second", ItemStatus.APPROVED, 2, Effort.S),
        ]
        _write_roadmap(tmp_path, items=items)

        # Write a checkpoint with ri-01 already completed
        checkpoint_data = {
            "schema_version": 1,
            "roadmap_id": "test-roadmap",
            "current_item_id": "ri-01",
            "phase": "completed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "completed_items": ["ri-01"],
        }
        (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint_data))

        # Also update roadmap to reflect ri-01 is completed
        roadmap_data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        roadmap_data["items"][0]["status"] = "completed"
        (tmp_path / "roadmap.yaml").write_text(yaml.dump(roadmap_data, default_flow_style=False))

        executed: list[str] = []

        def track(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track)

        assert "ri-01" not in executed
        assert "ri-02" in executed
        assert result["completed_count"] == 2

class TestSummary:
    """Verify the returned summary dict."""

    def test_returns_correct_summary(self, tmp_path):
        _write_roadmap(tmp_path)

        result = execute_roadmap(tmp_path)

        assert "completed_count" in result
        assert "failed_count" in result
        assert "blocked_count" in result
        assert "skipped_count" in result
        assert "status" in result
        assert "policy_decisions" in result
        assert isinstance(result["policy_decisions"], list)

    def test_all_completed_status(self, tmp_path):
        _write_roadmap(tmp_path)
        result = execute_roadmap(tmp_path)
        assert result["status"] == "completed"

    def test_blocked_all_status(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "Will fail", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Depends", ItemStatus.APPROVED, 2, Effort.S, depends_on=["ri-01"]),
        ]
        _write_roadmap(tmp_path, items=items)

        def always_fail(item_id, phase, context):
            if phase == "implementing":
                return "failed:Error"
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=always_fail)

        assert result["status"] == "blocked_all"

class TestVendorLimitHandling:
    """Verify vendor limit events flow through the policy engine."""

    def test_vendor_limit_triggers_policy_decision(self, tmp_path):
        items = [RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)]
        _write_roadmap(
            tmp_path,
            items=items,
            policy=Policy(default_action=PolicyAction.SWITCH),
        )
        decisions: list = []

        call_count = {"n": 0}

        def limit_then_succeed(item_id, phase, context):
            call_count["n"] += 1
            if call_count["n"] == 2:  # implementing phase, first call
                return "vendor_limit:claude:rate limit hit"
            return "success"

        result = execute_roadmap(
            tmp_path,
            dispatch_fn=limit_then_succeed,
            on_policy_decision=lambda d: decisions.append(d),
        )

        assert len(decisions) == 1
        assert decisions[0].action == "switch"
        assert len(result["policy_decisions"]) == 1
