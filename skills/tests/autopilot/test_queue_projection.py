"""Contract tests for coordinated Autopilot phase projection (ri-09)."""

from __future__ import annotations

import json
from pathlib import Path

import autopilot
import pytest

import queue_projection


def _state(**overrides: object) -> autopilot.LoopState:
    values = {
        "change_id": "mirror-phase",
        "current_phase": "IMPLEMENT",
        "total_iterations": 7,
    }
    values.update(overrides)
    return autopilot.LoopState(**values)


def _ok(task_id: str = "current", *, cancelled: list[str] | None = None) -> dict:
    return {
        "status": "ok",
        "response": {
            "success": True,
            "task_id": task_id,
            "cancelled_task_ids": cancelled or [],
        },
    }


def test_submit_derives_exact_identity_and_repairs_owned_labels(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_submit_work",
        lambda **kw: calls.append(("submit", kw)) or _ok(),
    )
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_projection_issue_update",
        lambda **kw: calls.append(("update", kw)) or {"status": "ok"},
    )

    result = queue_projection.QueueProjectionAdapter(
        http_url="https://coordinator.invalid", api_key="secret"
    )(_state(), mode="submit")

    submit = calls[0][1]
    assert submit["projection_key"] == {
        "change_id": "mirror-phase",
        "phase": "IMPLEMENT",
        "transition_sequence": 7,
    }
    assert submit["task_type"] == "issue"
    assert submit["priority"] == 1
    assert set(submit["input_data"]) <= {
        "change_path",
        "execution_tier",
        "projection_provenance",
    }
    assert calls[1][1]["labels"] == [
        "change:mirror-phase",
        "projection:autopilot-phase",
    ]
    assert "secret" not in json.dumps(result)


def test_only_exact_reconciliation_required_conflict_advances_head(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_submit_work",
        lambda **kw: calls.append("submit")
        or {
            "status": "error",
            "status_code": 409,
            "response": {"detail": "reconciliation_required"},
        },
    )
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_reconcile_work_projection",
        lambda **kw: calls.append("reconcile") or _ok(),
    )
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_projection_issue_update",
        lambda **kw: {"status": "ok"},
    )

    assert queue_projection.QueueProjectionAdapter(http_url="x")(
        _state(), mode="submit"
    )["status"] == "ok"
    assert calls == ["submit", "reconcile"]

    calls.clear()
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_submit_work",
        lambda **kw: calls.append("submit")
        or {
            "status": "error",
            "status_code": 409,
            "response": {"detail": "projection_generation_mismatch"},
        },
    )
    result = queue_projection.QueueProjectionAdapter(http_url="x")(
        _state(), mode="submit"
    )
    assert result["status"] == "degraded"
    assert calls == ["submit"]


def test_reconcile_cleans_only_double_labelled_noncanonical_rows(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_reconcile_work_projection",
        lambda **kw: _ok("canonical", cancelled=["cancelled"]),
    )
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_projection_issue_list",
        lambda **kw: {
            "status": "ok",
            "response": {"issues": [{"id": "canonical"}, {"id": "leftover"}]},
        },
    )
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_projection_issue_update",
        lambda **kw: calls.append(kw) or {"status": "ok"},
    )

    result = queue_projection.QueueProjectionAdapter(http_url="x")(
        _state(), mode="reconcile"
    )

    assert result["status"] == "ok"
    assert {c["issue_id"] for c in calls if c["labels"] == []} == {
        "cancelled",
        "leftover",
    }


def test_projection_rejects_stricter_change_id_before_transport(monkeypatch) -> None:
    monkeypatch.setattr(
        queue_projection.bridge,
        "try_submit_work",
        lambda **kw: pytest.fail("transport must not be called"),
    )
    result = queue_projection.QueueProjectionAdapter(http_url="x")(
        _state(change_id="UPPER_case"), mode="submit"
    )
    assert result == {"status": "degraded", "reason": "invalid_change_id"}


def test_direct_escalation_advances_projection_sequence_once() -> None:
    state = _state(total_iterations=10)
    autopilot.enter_escalate(state, "boom")
    assert state.current_phase == "ESCALATE"
    assert state.total_iterations == 11


def test_persist_and_project_never_projects_after_failed_save(
    tmp_path: Path, monkeypatch
) -> None:
    called = False

    def projection(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(autopilot, "save_state", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        autopilot.persist_and_project(_state(), tmp_path / "state.json", projection)
    assert called is False
