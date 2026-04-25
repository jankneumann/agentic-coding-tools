"""Tests for LoopState schema_version=2 bump (Layer 1 wiring).

Asserts:
- LoopState carries a `last_handoff_id: str | None` field defaulting to None.
- schema_version bumps from 1 to 2.
- Existing v1 snapshots load without migration (last_handoff_id defaults to None).
- save_state → load_state round-trips preserve last_handoff_id.

Spec reference: skill-workflow / Coordinator Handoff Population at Autopilot
Phase Boundaries — Existing autopilot snapshots load without migration.
"""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from autopilot import LoopState, load_state, save_state  # noqa: E402


class TestLoopStateFieldShape:
    """LoopState exposes last_handoff_id and bumped schema_version."""

    def test_last_handoff_id_field_exists(self) -> None:
        names = {f.name for f in fields(LoopState)}
        assert "last_handoff_id" in names

    def test_last_handoff_id_default_is_none(self) -> None:
        state = LoopState()
        assert state.last_handoff_id is None

    def test_schema_version_is_two(self) -> None:
        state = LoopState()
        assert state.schema_version == 2

    def test_handoff_ids_still_present(self) -> None:
        # Don't break the existing handoff_ids list — both fields coexist.
        names = {f.name for f in fields(LoopState)}
        assert "handoff_ids" in names
        state = LoopState()
        assert state.handoff_ids == []


class TestBackwardCompatSnapshotLoad:
    """A v1 snapshot (no last_handoff_id, schema_version=1) loads cleanly."""

    def test_v1_snapshot_loads_with_default(self, tmp_path: Path) -> None:
        # Simulate a snapshot written by the v1 code path: no last_handoff_id
        # field at all, schema_version=1.
        v1_snapshot = {
            "schema_version": 1,
            "change_id": "old-change",
            "current_phase": "IMPLEMENT",
            "iteration": 2,
            "total_iterations": 5,
            "max_phase_iterations": 3,
            "findings_trend": [3, 1],
            "blocking_findings": [],
            "vendor_availability": {},
            "packages_status": {},
            "package_authors": {},
            "implementation_strategy": {},
            "memory_ids": [],
            "handoff_ids": ["h-1"],
            "started_at": "2026-04-25T00:00:00+00:00",
            "phase_started_at": "2026-04-25T00:01:00+00:00",
            "previous_phase": "PLAN_REVIEW",
            "escalation_reason": None,
            "val_review_enabled": False,
            "cli_review_enabled": True,
            "error": None,
        }
        path = tmp_path / "v1.json"
        path.write_text(json.dumps(v1_snapshot))

        state = load_state(path)
        # Loaded state has last_handoff_id defaulting to None; existing fields
        # preserved as-is.
        assert state.last_handoff_id is None
        assert state.change_id == "old-change"
        assert state.current_phase == "IMPLEMENT"
        assert state.handoff_ids == ["h-1"]

    def test_v1_snapshot_with_extra_fields_does_not_raise(
        self, tmp_path: Path,
    ) -> None:
        # load_state filters unknown keys, so a snapshot with extra fields
        # (e.g., a future-version or unrelated metadata) loads cleanly.
        snapshot = {
            "schema_version": 1,
            "change_id": "x",
            "_unknown_future_field": "ignored",
        }
        path = tmp_path / "extra.json"
        path.write_text(json.dumps(snapshot))
        state = load_state(path)
        assert state.change_id == "x"
        assert state.last_handoff_id is None


class TestRoundTrip:
    """save_state → load_state preserves last_handoff_id."""

    def test_roundtrip_preserves_last_handoff_id(self, tmp_path: Path) -> None:
        original = LoopState(
            change_id="rt",
            handoff_ids=["h-1", "h-2"],
            last_handoff_id="h-2",
        )
        path = tmp_path / "rt.json"
        save_state(original, path)
        loaded = load_state(path)
        assert loaded.last_handoff_id == "h-2"
        assert loaded.handoff_ids == ["h-1", "h-2"]
        assert loaded.schema_version == 2

    def test_roundtrip_with_none(self, tmp_path: Path) -> None:
        original = LoopState(change_id="rt", last_handoff_id=None)
        path = tmp_path / "rt2.json"
        save_state(original, path)
        loaded = load_state(path)
        assert loaded.last_handoff_id is None

    def test_serialized_form_includes_last_handoff_id(
        self, tmp_path: Path,
    ) -> None:
        # On-disk JSON must include the new field so other tooling can read it.
        state = LoopState(change_id="rt", last_handoff_id="h-99")
        path = tmp_path / "j.json"
        save_state(state, path)
        body = json.loads(path.read_text())
        assert "last_handoff_id" in body
        assert body["last_handoff_id"] == "h-99"
        assert body["schema_version"] == 2
