"""End-to-end test: seeder run for a fixture change-id → simulate coordinator
state → invoke renderer → assert tasks.md managed block reflects state.

Exercises the renderer + seeder together against a single in-memory
coordinator stub. Verifies the composite flow without requiring an actual
coordinator HTTP service.

Covers task 5.1.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills/coordinator-task-status-renderer/scripts"
_BRIDGE_SCRIPTS = _REPO_ROOT / "skills/coordination-bridge/scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))


class StubCoordinator:
    """In-memory coordinator that records issues and serves list/show."""

    def __init__(self):
        self.issues: list[dict[str, Any]] = []
        self._next_id = 1

    def try_issue_create(self, **kwargs):
        uid = f"u-{self._next_id}"
        self._next_id += 1
        issue = {
            "id": uid,
            "title": kwargs.get("title"),
            "status": "pending",
            "labels": list(kwargs.get("labels") or []),
            "depends_on": list(kwargs.get("depends_on") or []),
        }
        self.issues.append(issue)
        return {"status": "ok", "data": {"id": uid}}

    def try_issue_list(self, **kwargs):
        filter_labels = set(kwargs.get("labels") or [])
        out = []
        for iss in self.issues:
            iss_labels = set(iss.get("labels") or [])
            if filter_labels and not filter_labels.issubset(iss_labels):
                continue
            out.append(dict(iss))
        return {"status": "ok", "data": {"issues": out}}

    def set_status(self, task_key: str, status: str, **extra) -> None:
        for iss in self.issues:
            if any(lbl == f"task:{task_key}" for lbl in iss.get("labels", [])):
                iss["status"] = status
                iss.update(extra)
                return
        raise KeyError(f"no issue with task:{task_key}")


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    change_id = "demo-e2e"
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text(
        "# Tasks — demo-e2e\n\n"
        "Hand-authored intro paragraph.\n\n"
        "- [ ] 1.1 First task\n"
        "  **Dependencies**: None\n"
        "- [ ] 1.2 Second task\n"
        "  **Dependencies**: 1.1\n"
    )
    return tmp_path


def test_end_to_end_seed_then_render_reflects_coordinator_state(
    fake_repo, monkeypatch
):
    """Seed two tasks, mark 1.1 completed and 1.2 claimed, then render.

    Expected managed block contents:
      - [x] 1.1: First task — done by alice 2026-05-15
      - [ ] 1.2: Second task — claimed by bob
    """
    stub = StubCoordinator()
    # Monkey-patch BOTH scripts' references to the bridge.
    import seed_tasks_from_md as s
    import render_tasks_status as r

    monkeypatch.setattr(s.coordination_bridge, "try_issue_create", stub.try_issue_create)
    monkeypatch.setattr(s.coordination_bridge, "try_issue_list", stub.try_issue_list)
    monkeypatch.setattr(r.coordination_bridge, "try_issue_list", stub.try_issue_list)

    # 1. Seed
    assert s.seed("demo-e2e", fake_repo) == 0
    assert len(stub.issues) == 2

    # 2. Mutate coordinator state.
    stub.set_status(
        "1.1",
        "completed",
        assignee="alice",
        completed_at="2026-05-15T12:00:00Z",
    )
    stub.set_status("1.2", "claimed", assignee="bob")

    # 3. Render
    assert r.render("demo-e2e", fake_repo) == 0

    text = (fake_repo / "openspec/changes/demo-e2e/tasks.md").read_text()
    # Managed block exists.
    assert "<!-- GENERATED: begin coordinator:tasks-status -->" in text
    assert "<!-- GENERATED: end coordinator:tasks-status -->" in text
    # 1.1 completed -> checked, done annotation.
    assert "- [x] 1.1: First task — done by alice 2026-05-15" in text
    # 1.2 claimed -> unchecked, claimed annotation.
    assert "- [ ] 1.2: Second task — claimed by bob" in text
    # Hand-authored content preserved.
    assert "Hand-authored intro paragraph." in text


def test_e2e_idempotency_seed_twice(fake_repo, monkeypatch):
    """Running the seeder twice creates issues once."""
    stub = StubCoordinator()
    import seed_tasks_from_md as s

    monkeypatch.setattr(s.coordination_bridge, "try_issue_create", stub.try_issue_create)
    monkeypatch.setattr(s.coordination_bridge, "try_issue_list", stub.try_issue_list)
    assert s.seed("demo-e2e", fake_repo) == 0
    first_count = len(stub.issues)
    assert s.seed("demo-e2e", fake_repo) == 0
    assert len(stub.issues) == first_count, "second seed must not duplicate"
