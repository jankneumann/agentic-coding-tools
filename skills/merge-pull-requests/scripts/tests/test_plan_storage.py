"""Tests for merge plan storage tier selection (tasks 3.1 and 3.2)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_storage import (  # noqa: E402
    CoordinatorPlanStore,
    FilePlanStore,
    select_plan_store,
)
from test_merge_plan_contract import valid_plan  # noqa: E402


def test_file_store_is_authoritative_without_coordinator(tmp_path: Path) -> None:
    path = tmp_path / "merge-plan.json"
    with patch(
        "plan_storage._get_coordinator_status",
        return_value={"COORDINATOR_AVAILABLE": False, "CAN_QUEUE_WORK": False},
    ):
        store = select_plan_store(path)

    assert isinstance(store, FilePlanStore)
    store.save(valid_plan())
    assert store.load() == valid_plan()
    assert path.with_suffix(".md").exists()


def test_live_state_update_preserves_definition_fields(tmp_path: Path) -> None:
    path = tmp_path / "merge-plan.json"
    store = FilePlanStore(path)
    plan = valid_plan()
    definitions = copy.deepcopy([node["definition"] for node in plan["nodes"]])
    store.save(plan)

    store.update_state(10, outcome="merged", blocking_reason=None)

    updated = json.loads(path.read_text(encoding="utf-8"))
    assert [node["definition"] for node in updated["nodes"]] == definitions
    assert updated["nodes"][0]["state"]["outcome"] == "merged"


def test_coordinator_storage_is_an_explicit_phase_two_seam(tmp_path: Path) -> None:
    with patch(
        "plan_storage._get_coordinator_status",
        return_value={"COORDINATOR_AVAILABLE": True, "CAN_QUEUE_WORK": True},
    ):
        store = select_plan_store(tmp_path / "merge-plan.json")

    assert isinstance(store, CoordinatorPlanStore)
    with pytest.raises(NotImplementedError, match="Phase 2"):
        store.load()


def test_load_repairs_a_missing_or_stale_projection(tmp_path: Path) -> None:
    path = tmp_path / "merge-plan.json"
    store = FilePlanStore(path)
    store.save(valid_plan())
    path.with_suffix(".md").write_text("stale projection", encoding="utf-8")

    store.load()

    repaired = path.with_suffix(".md").read_text(encoding="utf-8")
    assert repaired.startswith("# Merge Plan")
    assert "stale projection" not in repaired
