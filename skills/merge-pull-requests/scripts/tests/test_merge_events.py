"""Tests for merge event schema, serialization, and JSONL emission.

Covers spec scenarios:
- merge-infrastructure.5: Merge event emission

Design decisions:
- D6: Metrics schema (JSONL + coordinator audit dual-write)
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_events import MergeEvent, emit_event, load_events


class TestMergeEventDataclass:
    """Verify MergeEvent structure matches the D6 schema."""

    def test_required_fields(self) -> None:
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        assert event.event_type == "merge"
        assert event.pr_number == 42
        assert event.backend == "direct"
        assert event.success is True

    def test_timestamp_auto_generated(self) -> None:
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        assert event.timestamp is not None
        # Should be a valid ISO 8601 string
        datetime.fromisoformat(event.timestamp)

    def test_optional_fields_default_none(self) -> None:
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        assert event.origin is None
        assert event.strategy is None
        assert event.duration_seconds is None
        assert event.queue_depth is None
        assert event.partition_count is None
        assert event.train_id is None
        assert event.error is None

    def test_all_fields_populated(self) -> None:
        event = MergeEvent(
            event_type="train_compose",
            pr_number=42,
            origin="openspec",
            strategy="rebase",
            backend="coordinator_train",
            duration_seconds=12.5,
            queue_depth=7,
            partition_count=3,
            train_id="abc123",
            success=True,
            error=None,
        )
        assert event.duration_seconds == 12.5
        assert event.queue_depth == 7
        assert event.partition_count == 3
        assert event.train_id == "abc123"

    def test_valid_event_types(self) -> None:
        for event_type in ("merge", "revert", "rebase", "eject", "train_compose"):
            event = MergeEvent(
                event_type=event_type,
                pr_number=1,
                backend="direct",
                success=True,
            )
            assert event.event_type == event_type

    def test_to_dict_returns_all_fields(self) -> None:
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        d = event.to_dict()
        assert "timestamp" in d
        assert "event_type" in d
        assert "pr_number" in d
        assert "backend" in d
        assert "success" in d

    def test_to_json_is_valid_json(self) -> None:
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "merge"
        assert parsed["pr_number"] == 42


class TestEmitEvent:
    """Test emit_event() writes to JSONL file."""

    def test_emit_appends_to_jsonl(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=True,
        )
        emit_event(event, log_path=log_path)

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["pr_number"] == 42

    def test_emit_multiple_events_appends(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for i in range(3):
            event = MergeEvent(
                event_type="merge",
                pr_number=i,
                backend="direct",
                success=True,
            )
            emit_event(event, log_path=log_path)

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0])["pr_number"] == 0
        assert json.loads(lines[2])["pr_number"] == 2

    def test_emit_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "sub" / "dir" / "metrics.jsonl"
        event = MergeEvent(
            event_type="merge",
            pr_number=1,
            backend="direct",
            success=True,
        )
        emit_event(event, log_path=log_path)
        assert log_path.exists()

    def test_emit_with_error_field(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        event = MergeEvent(
            event_type="merge",
            pr_number=42,
            backend="direct",
            success=False,
            error="Merge conflicts detected",
        )
        emit_event(event, log_path=log_path)

        parsed = json.loads(log_path.read_text().strip())
        assert parsed["success"] is False
        assert parsed["error"] == "Merge conflicts detected"


class TestLoadEvents:
    """Test load_events() reads JSONL file."""

    def test_load_from_jsonl(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for i in range(3):
            event = MergeEvent(
                event_type="merge",
                pr_number=i,
                backend="direct",
                success=True,
            )
            emit_event(event, log_path=log_path)

        events = load_events(log_path=log_path)
        assert len(events) == 3
        assert all(isinstance(e, dict) for e in events)

    def test_load_from_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nope.jsonl"
        events = load_events(log_path=log_path)
        assert events == []

    def test_load_filters_by_event_type(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for et in ("merge", "rebase", "merge", "revert"):
            event = MergeEvent(
                event_type=et,
                pr_number=1,
                backend="direct",
                success=True,
            )
            emit_event(event, log_path=log_path)

        events = load_events(log_path=log_path, event_type="merge")
        assert len(events) == 2
